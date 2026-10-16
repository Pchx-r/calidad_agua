import tkinter as tk
import serial
import threading
import time

PUERTO_COM = 'COM7'
BAUDIOS = 115200


class MonitorAguaPro:
    def __init__(self, root):
        self.root = root
        self.root.title("Monitor de Calidad del Agua - ESP32")
        self.root.geometry("800x700")
        self.root.configure(bg="#050d18")

        # Variables de estado
        self.tds = 0
        self.historial = []
        self.mn = 9999
        self.mx = 0
        self.sum = 0
        self.count = 0
        self.ser = None
        self.leyendo = True

        # Estilos compartidos
        self.bg_color = "#050d18"
        self.card_color = "#0a1522"
        self.lbl_color = "#344f68"
        self.text_color = "#c0d8f0"

        self.crear_interfaz()

        self.root.protocol("WM_DELETE_WINDOW", self.al_cerrar)
        self.root.after(100, self.actualizar_ui)

    def crear_interfaz(self):
        # Header
        header = tk.Frame(self.root, bg=self.bg_color)
        header.pack(fill="x", padx=20, pady=10)
        tk.Label(header, text="SISTEMA DE MONITOREO — ESP32\n💧 Monitor de Calidad del Agua",
                 font=("Segoe UI", 16, "bold"), bg=self.bg_color, fg="#deeeff", justify="left").pack(side="left")

        self.btn_conectar = tk.Button(header, text="🔌 Conectar ESP32", bg="#0077cc", fg="white",
                                      command=self.conectar_serial, font=("Segoe UI", 10, "bold"), relief="flat")
        self.btn_conectar.pack(side="right", padx=10)

        # Fila 1: Gauge y Estado
        f1 = tk.Frame(self.root, bg=self.bg_color)
        f1.pack(fill="x", padx=20, pady=10)

        # Gauge Card
        self.card_gauge = tk.Frame(f1, bg=self.card_color, bd=1, relief="solid")
        self.card_gauge.pack(side="left", fill="both", expand=True, padx=(0, 5))
        tk.Label(self.card_gauge, text="MEDICIÓN ACTUAL", bg=self.card_color, fg=self.lbl_color,
                 font=("Segoe UI", 10, "bold")).pack(pady=5)
        self.canvas_gauge = tk.Canvas(self.card_gauge, width=220, height=175, bg=self.card_color, highlightthickness=0)
        self.canvas_gauge.pack(pady=10)

        # Estado Card
        self.card_estado = tk.Frame(f1, bg=self.card_color, bd=1, relief="solid")
        self.card_estado.pack(side="right", fill="both", expand=True, padx=(5, 0))
        tk.Label(self.card_estado, text="ESTADO DEL SISTEMA", bg=self.card_color, fg=self.lbl_color,
                 font=("Segoe UI", 10, "bold")).pack(pady=5)

        # LCD Simulado
        self.lcd_frame = tk.Frame(self.card_estado, bg="#0b1e0f", bd=2, relief="solid")
        self.lcd_frame.pack(fill="x", padx=20, pady=5)
        self.lbl_lcd1 = tk.Label(self.lcd_frame, text="TDS: 0000 ppm", bg="#0b1e0f", fg="#33ff88",
                                 font=("Courier New", 14, "bold"))
        self.lbl_lcd1.pack(anchor="w", padx=10)
        self.lbl_lcd2 = tk.Label(self.lcd_frame, text="Calidad: BUENA", bg="#0b1e0f", fg="#33ff88",
                                 font=("Courier New", 14, "bold"))
        self.lbl_lcd2.pack(anchor="w", padx=10)

        # Estado en texto grande + mensaje de alerta
        self.lbl_estado_txt = tk.Label(self.card_estado, text="BUENA", bg=self.card_color, fg="#00e87a",
                                       font=("Courier New", 28, "bold"))
        self.lbl_estado_txt.pack(pady=(10, 0))
        self.lbl_alerta = tk.Label(self.card_estado, text="Agua en buen estado", bg=self.card_color,
                                   fg="#00e87a", font=("Segoe UI", 11, "bold"), wraplength=300)
        self.lbl_alerta.pack(pady=(0, 10))

        # Fila 2: Gráfico Histórico
        f2 = tk.Frame(self.root, bg=self.card_color, bd=1, relief="solid")
        f2.pack(fill="x", padx=20, pady=10)
        tk.Label(f2, text="HISTORIAL — ÚLTIMAS 60 LECTURAS", bg=self.card_color, fg=self.lbl_color,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=5)
        self.canvas_chart = tk.Canvas(f2, width=750, height=150, bg=self.card_color, highlightthickness=0)
        self.canvas_chart.pack(pady=10)

        # Fila 3: Estadísticas
        f3 = tk.Frame(self.root, bg=self.bg_color)
        f3.pack(fill="x", padx=20, pady=10)

        self.card_stats = tk.Frame(f3, bg=self.card_color, bd=1, relief="solid")
        self.card_stats.pack(fill="both", expand=True)
        tk.Label(self.card_stats, text="ESTADÍSTICAS", bg=self.card_color, fg=self.lbl_color,
                 font=("Segoe UI", 10, "bold")).pack(pady=5)
        self.lbl_stats = tk.Label(self.card_stats, text="Mín: 0 | Máx: 0 | Prom: 0", bg=self.card_color, fg="#00aaee",
                                  font=("Courier New", 18, "bold"))
        self.lbl_stats.pack(pady=20)

    def obtener_calidad(self, val):
        """Devuelve (texto, color, mensaje de alerta) según el ppm."""
        if val <= 100:
            return "BUENA", "#00e87a", "Agua en buen estado"
        if val < 350:
            return "REGULAR", "#ffc107", "⚠ Calidad regular: se recomienda vigilar"
        if val < 750:
            return "ALTO", "#ff8c1a", "⚠ TDS alto: no recomendada para consumo"
        return "PELIGRO", "#ff4455", "⛔ PELIGRO: TDS crítico, no usar el agua"

    def conectar_serial(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(PUERTO_COM, BAUDIOS, timeout=1)
            self.btn_conectar.config(text="🔌 Conectado", bg="#00e87a")
            threading.Thread(target=self.leer_datos_serial, daemon=True).start()
        except Exception:
            self.btn_conectar.config(text="⚠️ Error COM", bg="#ff4455")

    def leer_datos_serial(self):
        while self.leyendo:
            if self.ser and self.ser.is_open:
                try:
                    if self.ser.in_waiting > 0:
                        linea = self.ser.readline().decode('utf-8', errors='ignore').strip()
                        if linea:
                            self.root.after(0, self.registrar_lectura, float(linea))
                except Exception:
                    pass
            time.sleep(0.05)

    def registrar_lectura(self, val):
        self.tds = val
        self.historial.append(val)
        if len(self.historial) > 60:
            self.historial.pop(0)
        self.mn = min(self.mn, val)
        self.mx = max(self.mx, val)
        self.sum += val
        self.count += 1

    def actualizar_ui(self):
        txt, color, alerta = self.obtener_calidad(self.tds)

        # LCD simulado y estado
        self.lbl_lcd1.config(text=f"TDS: {int(self.tds):04d} ppm")
        self.lbl_lcd2.config(text=f"Calidad: {txt}", fg=color)
        self.lbl_estado_txt.config(text=txt, fg=color)
        self.lbl_alerta.config(text=alerta, fg=color)

        # Gauge
        self.canvas_gauge.delete("all")
        cx, cy, r = 110, 120, 80
        self.canvas_gauge.create_arc(cx - r, cy - r, cx + r, cy + r, start=-30, extent=240, style="arc",
                                     outline="#101e30", width=15)
        pct = min(self.tds / 1000, 1)
        if pct > 0:
            self.canvas_gauge.create_arc(cx - r, cy - r, cx + r, cy + r, start=210 - (pct * 240), extent=pct * 240,
                                         style="arc", outline=color, width=15)
        self.canvas_gauge.create_text(cx, cy - 10, text=str(int(self.tds)), fill=color,
                                      font=("Courier New", 32, "bold"))
        self.canvas_gauge.create_text(cx, cy + 20, text="ppm TDS", fill="#3a5268", font=("Segoe UI", 10))

        # Gráfico histórico con las líneas de los umbrales
        self.canvas_chart.delete("all")
        w, h = 750, 150
        for limite, c in ((100, "#00e87a"), (350, "#ffc107"), (750, "#ff4455")):
            y = h - (limite / 1000) * h
            self.canvas_chart.create_line(0, y, w, y, fill=c, dash=(4, 4))
        if len(self.historial) > 1:
            dx = w / 59
            puntos = []
            for i, val in enumerate(self.historial):
                y = h - (min(val, 1000) / 1000) * h
                puntos.extend([i * dx, y])
            self.canvas_chart.create_line(puntos, fill="#0099ee", width=2)

        # Estadísticas
        prom = self.sum / self.count if self.count > 0 else 0
        m_val = self.mn if self.count > 0 else 0
        self.lbl_stats.config(text=f"Mín: {int(m_val)} | Máx: {int(self.mx)} | Prom: {int(prom)}")

        self.root.after(100, self.actualizar_ui)

    def al_cerrar(self):
        self.leyendo = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.root.destroy()


if __name__ == "__main__":
    ventana = tk.Tk()
    app = MonitorAguaPro(ventana)
    ventana.mainloop()