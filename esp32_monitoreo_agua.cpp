#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// Pantalla LCD (dirección 0x27, 16 columnas, 2 filas)
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Pin analógico del sensor TDS (ADC1, compatible con el ESP32)
#define TdsSensorPin 34

// Configuración del ADC del ESP32
#define VREF 3.3
#define ADC_RES 4095.0

// Umbrales de calidad (ppm)
#define LIMITE_BUENA 100
#define LIMITE_REGULAR 350
#define LIMITE_ALTO 750

// Umbral de "sin agua"
#define LIMITE_SIN_AGUA 20

// Detección de sensor desconectado con histéresis
#define VARIACION_MINIMA 15.0      // ppm de diferencia para contar como "salto"
#define CICLOS_SALTANDO 5          // 5 saltos seguidos → activa DESCONECTADO
#define CICLOS_ESTABLES 3          // 3 lecturas estables seguidas → desactiva

float lecturaPrevia = -1;
int contadorSaltos = 0;
int contadorEstables = 0;
bool estadoDesconectado = false;

// Devuelve el texto de calidad según el ppm
const char* obtenerCalidad(float ppm) {
  if (ppm < LIMITE_SIN_AGUA) return "SIN AGUA";
  if (ppm <= LIMITE_BUENA)   return "BUENA";
  if (ppm <  LIMITE_REGULAR) return "REGULAR";
  if (ppm <  LIMITE_ALTO)    return "ALTO";
  return "PELIGRO";
}

// Detecta si el sensor está desconectado con histéresis
bool sensorDesconectado(float ppm) {
  if (lecturaPrevia < 0) {
    lecturaPrevia = ppm;
    return false;
  }

  float variacion = fabs(ppm - lecturaPrevia);
  lecturaPrevia = ppm;
  bool haySalto = (variacion > VARIACION_MINIMA);

  if (!estadoDesconectado) {
    // MODO NORMAL: detectar cuándo entrar a DESCONECTADO
    if (haySalto) {
      contadorSaltos++;
      if (contadorSaltos >= CICLOS_SALTANDO) {
        estadoDesconectado = true;
        contadorEstables = 0;
      }
    } else {
      contadorSaltos = 0;
    }
  } else {
    // MODO DESCONECTADO: detectar cuándo volver a normal
    if (haySalto) {
      contadorEstables = 0;
    } else {
      contadorEstables++;
      if (contadorEstables >= CICLOS_ESTABLES) {
        estadoDesconectado = false;
        contadorSaltos = 0;
        contadorEstables = 0;
      }
    }
  }

  return estadoDesconectado;
}

void setup() {
  Serial.begin(115200);

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Iniciando...");
  lcd.setCursor(0, 1);
  lcd.print("Monitor de Agua");
  delay(2000);
  lcd.clear();

  pinMode(TdsSensorPin, INPUT);
}

void loop() {
  // 1. Leer el valor analógico (promediado)
  int acumulado = 0;
  for (int i = 0; i < 10; i++) {
    acumulado += analogRead(TdsSensorPin);
    delay(10);
  }
  float analogValue = acumulado / 10.0;

  // 2. Convertir a voltaje
  float voltage = analogValue * (VREF / ADC_RES);

  // 3. Voltaje a PPM
  float compensationCoefficient = 1.0;
  float compensationVoltage = voltage / compensationCoefficient;
  float tdsValue = (133.42 * pow(compensationVoltage, 3)
                  - 255.86 * pow(compensationVoltage, 2)
                  + 857.39 * compensationVoltage) * 0.5;

  if (tdsValue < 0) tdsValue = 0;

  // 4. Detectar sensor desconectado (con histéresis)
  bool desconectado = sensorDesconectado(tdsValue);

  // 5. Determinar el texto de calidad final
  const char* calidad;
  if (desconectado) {
    calidad = "DESCONECTADO";
  } else {
    calidad = obtenerCalidad(tdsValue);
  }

  // 6. SALIDA SERIAL LIMPIA (una sola cosa por línea)
  //    - "-1"          → sensor desconectado
  //    - "123.4"       → ppm normal (incluye "sin agua" cuando < 20)
  if (desconectado) {
    Serial.println("-1");
  } else {
    Serial.println(tdsValue, 1);
  }

  // 7. Mostrar en la LCD
  lcd.setCursor(0, 0);
  if (desconectado) {
    lcd.print("Sensor desconec.");
  } else {
    lcd.print("TDS: ");
    lcd.print((int)tdsValue);
    lcd.print(" ppm     ");
  }

  lcd.setCursor(0, 1);
  if (desconectado) {
    lcd.print("Revise conexion ");
  } else {
    lcd.print("Calidad: ");
    lcd.print(calidad);
    int len = 9 + strlen(calidad);
    for (int i = len; i < 16; i++) lcd.print(" ");
  }

  delay(1000);
}

  delay(1000);
}
