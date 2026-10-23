"""Reset the ESP32-S3 (USB-Serial/JTAG) and log serial output with host timestamps."""
import sys, time, serial
port, seconds, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
reset = len(sys.argv) < 5 or sys.argv[4] != "noreset"
start = time.time()
with open(out, "w") as log:
    for _ in range(50):
        try:
            ser = serial.Serial(port, 115200, timeout=0.2)
            break
        except (serial.SerialException, OSError):
            time.sleep(0.2)
    else:
        raise SystemExit(f"cannot open {port}")
    if reset:
        ser.dtr = False; ser.rts = True; time.sleep(0.1); ser.rts = False
        log.write(f"[{0.0:8.3f}] --- host: hard reset via RTS ---\n")
    buf = b""
    while time.time() - start < seconds:
        try:
            chunk = ser.read(4096)
        except (serial.SerialException, OSError):
            ser.close(); time.sleep(0.3)
            try: ser = serial.Serial(port, 115200, timeout=0.2)
            except Exception: pass
            continue
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            text = line.decode(errors="replace").rstrip("\r")
            log.write(f"[{time.time()-start:8.3f}] {text}\n"); log.flush()
print("done", out)
