#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// Pantalla LCD (dirección 0x27, 16 columnas, 2 filas)
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Pin analógico del sensor TDS (ADC1, compatible con el ESP32)
// Cambia este número si conectaste el sensor a otro pin.
#define TdsSensorPin 34

// Configuración del ADC del ESP32
#define VREF 3.3
#define ADC_RES 4095.0

// Umbrales de calidad (ppm)
#define LIMITE_BUENA 100
#define LIMITE_REGULAR 350
#define LIMITE_ALTO 750

// Devuelve el texto de calidad según el ppm
const char* obtenerCalidad(float ppm) {
  if (ppm <= LIMITE_BUENA)   return "BUENA";
  if (ppm <  LIMITE_REGULAR) return "REGULAR";
  if (ppm <  LIMITE_ALTO)    return "ALTO";
  return "PELIGRO";
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

  // 4. Enviar el valor al programa de Python (una lectura por línea)
  Serial.println(tdsValue, 1);

  // 5. Mostrar en la LCD
  const char* calidad = obtenerCalidad(tdsValue);

  lcd.setCursor(0, 0);
  lcd.print("TDS: ");
  lcd.print((int)tdsValue);
  lcd.print(" ppm     ");

  lcd.setCursor(0, 1);
  lcd.print("Calidad: ");
  lcd.print(calidad);
  lcd.print("   ");   // limpia restos de textos más largos

  delay(1000);
}