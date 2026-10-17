import tkinter as tk
import serial
import threading
import time
from datetime import datetime

PUERTO_COM = 'COM10'
BAUDIOS = 115200

# ---- Mismos parámetros que el Arduino ----
VARIACION_MINIMA = 15.0      # ppm de diferencia para contar como "salto"
CICLOS_SALTANDO = 5          # 5 saltos seguidos → activa DESCONECTADO
CICLOS_ESTABLES = 3          # 3 lecturas estables seguidas → desactiva


class MonitorAguaPro:
    def __init__(self, root):
        self.root = root
        self.root.title("Monitor de Calidad del Agua - ESP32")
        self.root.geometry("800x930")
        self.root.configure(bg="#050d18")

        # Variables de estado
        self.tds = 0
        self.historial = []
        self.mn = 9999
        self.mx = 0
        self.sum = 0
        self.count = 0
        self.conteo = {"BUENA": 0, "REGULAR": 0, "ALTO": 0, "PELIGRO": 0,
                       "SIN AGUA": 0, "DESCONECTADO": 0}
        self.ser = None
        self.leyendo = True

        # ---- Estado de desconexión con histéresis (igual que Arduino) ----
        self.lectura_previa = -1.0
        self.contador_saltos = 0
        self.contador_estables = 0
        self.estado_desconectado = False

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
        self.lbl_stats.pack(pady=(10, 5))
        self.lbl_conteo = tk.Label(self.card_stats, text="", bg=self.card_color, fg=self.text_color,
                                   font=("Courier New", 11, "bold"))
        self.lbl_conteo.pack(pady=(0, 10))

        # Fila 4: Resultados obtenidos
        f4 = tk.Frame(self.root, bg=self.card_color, bd=1, relief="solid")
        f4.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        tk.Label(f4, text="RESULTADOS OBTENIDOS", bg=self.card_color, fg=self.lbl_color,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=5)
        marco = tk.Frame(f4, bg=self.card_color)
        marco.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        scroll = tk.Scrollbar(marco)
        scroll.pack(side="right", fill="y")
        self.txt_resultados = tk.Text(marco, height=8, bg="#070f1a", fg=self.text_color, bd=0,
                                      font=("Courier New", 11), yscrollcommand=scroll.set, state="disabled")
        self.txt_resultados.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.txt_resultados.yview)
        for nombre, c in (
            ("BUENA", "#00e87a"),
            ("REGULAR", "#ffc107"),
            ("ALTO", "#ff8c1a"),
            ("PELIGRO", "#ff4455"),
            ("SIN AGUA", "#00c8ff"),
            ("DESCONECTADO", "#888888"),
        ):
            self.txt_resultados.tag_config(nombre, foreground=c)

    def obtener_calidad(self, val):
        """Devuelve (texto, color, mensaje de alerta) según el ppm.
           - val = -1  -> sensor desconectado
           - val < 20  -> sin agua
        """
        if val == -1:
            return "DESCONECTADO", "#888888", "🔌 Sensor desconectado: revise la conexión"
        if val < 20:
            return "SIN AGUA", "#00c8ff", "💧 Por favor ingrese agua al recipiente"
        if val <= 100:
            return "BUENA", "#00e87a", "Agua en buen estado"
        if val < 350:
            return "REGULAR", "#ffc107", "⚠ Calidad regular: se recomienda vigilar"
        if val < 750:
            return "ALTO", "#ff8c1a", "⚠ TDS alto: no recomendada para consumo"
        return "PELIGRO", "#ff4455", "⛔ PELIGRO: TDS crítico, no usar el agua"

    def detectar_desconexion(self, val):
        """Réplica exacta de sensorDesconectado() del Arduino.
        Devuelve True si el sensor está desconectado (con histéresis).
        """
        if self.lectura_previa < 0:
            self.lectura_previa = val
            return False

        variacion = abs(val - self.lectura_previa)
        self.lectura_previa = val
        hay_salto = (variacion > VARIACION_MINIMA)

        if not self.estado_desconectado:
            # MODO NORMAL: detectar cuándo entrar a DESCONECTADO
            if hay_salto:
                self.contador_saltos += 1
                if self.contador_saltos >= CICLOS_SALTANDO:
                    self.estado_desconectado = True
                    self.contador_estables = 0
            else:
                self.contador_saltos = 0
        else:
            # MODO DESCONECTADO: detectar cuándo volver a normal
            if hay_salto:
                self.contador_estables = 0
            else:
                self.contador_estables += 1
                if self.contador_estables >= CICLOS_ESTABLES:
                    self.estado_desconectado = False
                    self.contador_saltos = 0
                    self.contador_estables = 0

        return self.estado_desconectado

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
        # Caso especial: sensor desconectado (el ESP32 manda -1)
        if val == -1:
            # El Arduino ya confirmó la desconexión. Sincronizamos el estado
            # local para que la histéresis de Python también esté activa.
            self.estado_desconectado = True
            self.contador_saltos = CICLOS_SALTANDO
            self.contador_estables = 0
            # Reiniciar la lectura previa para que al reconectar no cuente
            # saltos artificiales.
            self.lectura_previa = -1.0

            txt = "DESCONECTADO"
            self.conteo[txt] += 1
            linea = f"{datetime.now():%H:%M:%S} |   ----   | {txt}\n"
            self.txt_resultados.config(state="normal")
            self.txt_resultados.insert("1.0", linea, txt)
            if int(self.txt_resultados.index("end-1c").split(".")[0]) > 200:
                self.txt_resultados.delete("200.0", "end")
            self.txt_resultados.config(state="disabled")
            self.tds = -1
            return

        # Caso normal: aplicar la histéresis local
        desconectado = self.detectar_desconexion(val)

        if desconectado:
            # El Arduino mandó un ppm, pero localmente detectamos desconexión
            # (por ejemplo, el estado aún no se había propagado).
            # Lo tratamos como desconectado.
            txt = "DESCONECTADO"
            self.conteo[txt] += 1
            linea = f"{datetime.now():%H:%M:%S} |   ----   | {txt}\n"
            self.txt_resultados.config(state="normal")
            self.txt_resultados.insert("1.0", linea, txt)
            if int(self.txt_resultados.index("end-1c").split(".")[0]) > 200:
                self.txt_resultados.delete("200.0", "end")
            self.txt_resultados.config(state="disabled")
            self.tds = -1
            return

        # Sensor OK: actualizar datos normalmente
        self.tds = val
        self.historial.append(val)
        if len(self.historial) > 60:
            self.historial.pop(0)
        self.mn = min(self.mn, val)
        self.mx = max(self.mx, val)
        self.sum += val
        self.count += 1

        txt, _, _ = self.obtener_calidad(val)
        self.conteo[txt] += 1
        linea = f"{datetime.now():%H:%M:%S} | {val:7.1f} ppm | {txt}\n"
        self.txt_resultados.config(state="normal")
        self.txt_resultados.insert("1.0", linea, txt)
        if int(self.txt_resultados.index("end-1c").split(".")[0]) > 200:
            self.txt_resultados.delete("200.0", "end")
        self.txt_resultados.config(state="disabled")

    def actualizar_ui(self):
        txt, color, alerta = self.obtener_calidad(self.tds)

        # LCD simulado y estado
        if self.tds == -1:
            self.lbl_lcd1.config(text="TDS: ---- ppm")
            self.lbl_lcd2.config(text="Sensor desconec.", fg=color)
        else:
            self.lbl_lcd1.config(text=f"TDS: {int(self.tds):04d} ppm")
            self.lbl_lcd2.config(text=f"Calidad: {txt}", fg=color)

        self.lbl_estado_txt.config(text=txt, fg=color)
        self.lbl_alerta.config(text=alerta, fg=color)

        # Gauge
        self.canvas_gauge.delete("all")
        cx, cy, r = 110, 120, 80
        self.canvas_gauge.create_arc(cx - r, cy - r, cx + r, cy + r, start=-30, extent=240, style="arc",
                                     outline="#101e30", width=15)

        if self.tds == -1:
            self.canvas_gauge.create_text(cx, cy - 10, text="--", fill=color,
                                          font=("Courier New", 32, "bold"))
            self.canvas_gauge.create_text(cx, cy + 20, text="sin sensor", fill="#3a5268",
                                          font=("Segoe UI", 10))
        else:
            pct = min(self.tds / 1000, 1)
            if pct > 0:
                self.canvas_gauge.create_arc(cx - r, cy - r, cx + r, cy + r,
                                             start=210 - (pct * 240), extent=pct * 240,
                                             style="arc", outline=color, width=15)
            self.canvas_gauge.create_text(cx, cy - 10, text=str(int(self.tds)), fill=color,
                                          font=("Courier New", 32, "bold"))
            self.canvas_gauge.create_text(cx, cy + 20, text="ppm TDS", fill="#3a5268",
                                          font=("Segoe UI", 10))

        # Gráfico histórico
        self.canvas_chart.delete("all")
        w, h = 750, 150
        for limite, c in ((20, "#00c8ff"), (100, "#00e87a"), (350, "#ffc107"), (750, "#ff4455")):
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
        c = self.conteo
        self.lbl_conteo.config(text=f"Lecturas: {self.count}  |  BUENA: {c['BUENA']}  REGULAR: {c['REGULAR']}  "
                                    f"ALTO: {c['ALTO']}  PELIGRO: {c['PELIGRO']}  "
                                    f"SIN AGUA: {c['SIN AGUA']}  DESCONECTADO: {c['DESCONECTADO']}")

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
