use std::io::Write;

fn main() {
    std::io::stdout()
        .write_all(b"\x1b[31mfusion-pty-ok\x1b[0m")
        .expect("terminal test helper could not write stdout");
}
