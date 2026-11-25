//! TDV 2200 keyboard USB adapter, Rust firmware. Milestone 1: sniffer.
//!
//! Receives what the keyboard sends (2400 baud on GP1) and prints it on a USB
//! serial port, one line per byte, decoded as raw-mode codes. Lines typed on
//! the serial port are sent to the keyboard (600 baud on GP4):
//!
//!   hex bytes, e.g. `24` or `32 24`   send them to the keyboard
//!   `baud 2400` / `baud 4800`         receive from the keyboard at that speed
//!                                     (send `3a` first to switch the keyboard)
//!   `boot`                            restart into the UF2 bootloader
//!   `help`                            list the commands
//!
//! Wiring as in adapter/build-sheet.html. The Pico's LED blinks for each byte
//! received from the keyboard.

#![no_std]
#![no_main]

use core::fmt::Write as _;

use embassy_executor::Spawner;
use embassy_futures::select::{Either, select};
use embassy_rp::bind_interrupts;
use embassy_rp::gpio::{Level, Output};
use embassy_rp::peripherals::{DMA_CH0, UART0, USB};
use embassy_rp::uart::{self, Async, BufferedInterruptHandler, BufferedUartRx, UartTx};
use embassy_rp::{dma, usb};
use embassy_sync::blocking_mutex::raw::CriticalSectionRawMutex;
use embassy_sync::channel::Channel;
use embassy_time::{Duration, Instant, Timer};
use embassy_usb::class::cdc_acm::{CdcAcmClass, Receiver, Sender, State};
use embassy_usb::{Builder, UsbDevice};
use embedded_io_async::Read;
use heapless::{String, Vec};
use static_cell::StaticCell;

bind_interrupts!(struct Irqs {
    USBCTRL_IRQ => usb::InterruptHandler<USB>;
    UART0_IRQ => BufferedInterruptHandler<UART0>;
    DMA_IRQ_0 => dma::InterruptHandler<DMA_CH0>;
});

const KBD_IN_BAUD: u32 = 2400; // keyboard -> adapter
const KBD_OUT_BAUD: u32 = 600; // adapter -> keyboard
const BURST_GAP_MS: u64 = 30; // a quiet gap this long starts a new group of lines
const USB_PACKET: usize = 64;

type UsbDriver = usb::Driver<'static, USB>;
type Line = String<96>;

/// What the keyboard sent, with the time it arrived.
#[derive(Clone, Copy)]
enum FromKbd {
    Byte(u8, Instant),
    Error(&'static str, Instant),
}

static FROM_KBD: Channel<CriticalSectionRawMutex, FromKbd, 128> = Channel::new();
static TO_KBD: Channel<CriticalSectionRawMutex, Vec<u8, 32>, 4> = Channel::new();
static CONSOLE: Channel<CriticalSectionRawMutex, Line, 8> = Channel::new();

#[embassy_executor::main(executor = "embassy_rp::executor::Executor", entry = "cortex_m_rt::entry")]
async fn main(spawner: Spawner) {
    let p = embassy_rp::init(Default::default());

    // Keyboard link
    let mut rx_cfg = uart::Config::default();
    rx_cfg.baudrate = KBD_IN_BAUD;
    static RX_BUF: StaticCell<[u8; 256]> = StaticCell::new();
    let kbd_rx = BufferedUartRx::new(p.UART0, Irqs, p.PIN_1, RX_BUF.init([0; 256]), rx_cfg);

    let mut tx_cfg = uart::Config::default();
    tx_cfg.baudrate = KBD_OUT_BAUD;
    let kbd_tx = UartTx::new(p.UART1, p.PIN_4, p.DMA_CH0, Irqs, tx_cfg);

    let led = Output::new(p.PIN_25, Level::Low);

    // USB: one serial port
    let mut config = embassy_usb::Config::new(0x1209, 0x0001);
    config.manufacturer = Some("tdv2200kbd");
    config.product = Some("TDV 2200 keyboard adapter (sniffer)");
    config.serial_number = Some("0001");
    config.max_power = 500; // the keyboard is powered from VBUS
    config.max_packet_size_0 = 64;

    static CONFIG_DESC: StaticCell<[u8; 256]> = StaticCell::new();
    static BOS_DESC: StaticCell<[u8; 256]> = StaticCell::new();
    static CONTROL_BUF: StaticCell<[u8; 64]> = StaticCell::new();
    static CDC_STATE: StaticCell<State> = StaticCell::new();

    let mut builder = Builder::new(
        usb::Driver::new(p.USB, Irqs),
        config,
        CONFIG_DESC.init([0; 256]),
        BOS_DESC.init([0; 256]),
        &mut [],
        CONTROL_BUF.init([0; 64]),
    );
    let serial = CdcAcmClass::new(&mut builder, CDC_STATE.init(State::new()), USB_PACKET as u16);
    let (usb_out, usb_in) = serial.split();

    spawner.spawn(usb_task(builder.build()).unwrap());
    spawner.spawn(kbd_rx_task(kbd_rx, led).unwrap());
    spawner.spawn(kbd_tx_task(kbd_tx).unwrap());
    spawner.spawn(console_in_task(usb_in).unwrap());
    console_out(usb_out).await;
}

#[embassy_executor::task]
async fn usb_task(mut device: UsbDevice<'static, UsbDriver>) -> ! {
    device.run().await
}

/// Keyboard -> FROM_KBD, with arrival times.
#[embassy_executor::task]
async fn kbd_rx_task(mut rx: BufferedUartRx, mut led: Output<'static>) -> ! {
    let mut buf = [0u8; 32];
    loop {
        let result = rx.read(&mut buf).await;
        let event_time = Instant::now();
        match result {
            Ok(n) => {
                for &b in &buf[..n] {
                    let _ = FROM_KBD.try_send(FromKbd::Byte(b, event_time));
                }
                led.toggle();
            }
            Err(e) => {
                let what = match e {
                    uart::Error::Framing => "framing error",
                    uart::Error::Parity => "parity error",
                    uart::Error::Overrun => "overrun",
                    uart::Error::Break => "break",
                    _ => "receive error",
                };
                let _ = FROM_KBD.try_send(FromKbd::Error(what, event_time));
            }
        }
    }
}

/// TO_KBD -> keyboard.
#[embassy_executor::task]
async fn kbd_tx_task(mut tx: UartTx<'static, Async>) -> ! {
    loop {
        let data = TO_KBD.receive().await;
        let _ = tx.write(&data).await;
    }
}

/// Lines typed on the serial port: echo them, and act on Enter.
#[embassy_executor::task]
async fn console_in_task(mut usb_in: Receiver<'static, UsbDriver>) -> ! {
    let mut line: String<64> = String::new();
    let mut packet = [0u8; USB_PACKET];
    loop {
        usb_in.wait_connection().await;
        while let Ok(n) = usb_in.read_packet(&mut packet).await {
            for &c in &packet[..n] {
                match c {
                    b'\r' | b'\n' => {
                        CONSOLE.send(text("\r\n")).await;
                        if !line.trim().is_empty() {
                            run_command(line.trim()).await;
                        }
                        line.clear();
                    }
                    0x08 | 0x7F => {
                        if line.pop().is_some() {
                            CONSOLE.send(text("\x08 \x08")).await;
                        }
                    }
                    0x20..=0x7E => {
                        if line.push(c as char).is_ok() {
                            let mut echo = Line::new();
                            let _ = echo.push(c as char);
                            CONSOLE.send(echo).await;
                        }
                    }
                    _ => {}
                }
            }
        }
    }
}

async fn run_command(cmd: &str) {
    match cmd {
        "help" => {
            CONSOLE.send(text("hex bytes (e.g. 24) = send to keyboard\r\n")).await;
            CONSOLE.send(text("baud 2400 | baud 4800 = receive speed\r\n")).await;
            CONSOLE.send(text("boot = UF2 bootloader\r\n")).await;
        }
        "baud 2400" | "baud 4800" => {
            let baud = if cmd.ends_with("4800") { 4800 } else { 2400 };
            set_kbd_in_baud(baud);
            let mut msg = Line::new();
            let _ = write!(msg, "receiving at {} baud\r\n", baud);
            CONSOLE.send(msg).await;
        }
        "boot" => {
            CONSOLE.send(text("restarting into the UF2 bootloader\r\n")).await;
            Timer::after(Duration::from_millis(100)).await; // let the message go out
            embassy_rp::rom_data::reset_to_usb_boot(1 << 25, 0);
        }
        _ => match parse_hex(cmd) {
            Some(bytes) if !bytes.is_empty() => {
                let mut msg = text(">> sent");
                for b in &bytes {
                    let _ = write!(msg, " {:02x}", b);
                }
                let _ = msg.push_str("\r\n");
                TO_KBD.send(bytes).await;
                CONSOLE.send(msg).await;
            }
            _ => CONSOLE.send(text("?? type hex bytes like: 24, or help\r\n")).await,
        },
    }
}

/// Change the receive speed from the keyboard (UART0). `BufferedUartRx` has
/// no method for it, so this sets the PL011 divisor the way embassy-rp does.
fn set_kbd_in_baud(baud: u32) {
    use embassy_rp::pac;
    let r = pac::UART0;
    let div = 8 * embassy_rp::clocks::clk_peri_freq() / baud;
    r.uartibrd().write_value(pac::uart::regs::Uartibrd(div >> 7));
    r.uartfbrd().write_value(pac::uart::regs::Uartfbrd(((div & 0x7f) + 1) / 2));
    r.uartlcr_h().modify(|_| {}); // the divisor takes effect on a write to LCR_H
}

fn parse_hex(s: &str) -> Option<Vec<u8, 32>> {
    let mut out = Vec::new();
    for tok in s.split(|c: char| c == ' ' || c == ',').filter(|t| !t.is_empty()) {
        out.push(u8::from_str_radix(tok, 16).ok()?).ok()?;
    }
    Some(out)
}

/// FROM_KBD and CONSOLE -> serial port.
async fn console_out(mut usb_out: Sender<'static, UsbDriver>) -> ! {
    let mut last: Option<Instant> = None;
    let mut special_next = false; // the byte after 00 is the special-column bitmap
    loop {
        usb_out.wait_connection().await;
        let _ = write_str(&mut usb_out, "\r\nTDV 2200 adapter (Rust) - sniffer. Type help.\r\n").await;
        loop {
            let line = match select(FROM_KBD.receive(), CONSOLE.receive()).await {
                Either::First(ev) => {
                    let (t, mut line) = match ev {
                        FromKbd::Byte(b, t) => (t, describe(b, &mut special_next)),
                        FromKbd::Error(what, t) => (t, text(what)),
                    };
                    let gap = last.map(|l| (t - l).as_millis()).unwrap_or(0);
                    last = Some(t);
                    let mut out = Line::new();
                    if gap > BURST_GAP_MS {
                        let _ = out.push_str("\r\n");
                    }
                    let _ = write!(out, "+{:6} ms  ", gap);
                    let _ = out.push_str(&line);
                    let _ = out.push_str("\r\n");
                    line.clear();
                    out
                }
                Either::Second(text) => text,
            };
            if write_str(&mut usb_out, &line).await.is_err() {
                break; // disconnected: wait for the next connection
            }
        }
    }
}

/// One byte from the keyboard, decoded as a raw-mode code.
fn describe(b: u8, special_next: &mut bool) -> Line {
    let mut s = Line::new();
    if *special_next {
        *special_next = false;
        let _ = write!(s, "{:02x}  special column = {:02x}", b, b);
    } else if b == 0x00 {
        *special_next = true;
        let _ = write!(s, "00  (special column follows)");
    } else if b < 0x80 {
        let _ = write!(s, "{:02x}  press   {:02x}", b, b);
    } else {
        let _ = write!(s, "{:02x}  release {:02x}", b, b & 0x7F);
    }
    s
}

fn text(s: &str) -> Line {
    let mut l = Line::new();
    let _ = l.push_str(s);
    l
}

/// Write a string as USB packets; a full last packet is followed by an empty
/// one so the computer doesn't wait for more.
async fn write_str(usb_out: &mut Sender<'static, UsbDriver>, s: &str) -> Result<(), ()> {
    let bytes = s.as_bytes();
    for chunk in bytes.chunks(USB_PACKET) {
        usb_out.write_packet(chunk).await.map_err(|_| ())?;
    }
    if !bytes.is_empty() && bytes.len() % USB_PACKET == 0 {
        usb_out.write_packet(&[]).await.map_err(|_| ())?;
    }
    Ok(())
}

/// On a crash, restart instead of hanging: the keyboard keeps working.
#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    cortex_m::peripheral::SCB::sys_reset();
}
