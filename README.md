GSA Cambios Bot — Pricing V1.0

Esta versión incorpora el Motor referencial de Pricing CLP→COP / BS→COP acordado para GSA Cambios.

Alcance V1

CLP→COP se calcula desde la economía proyectada CLP→USDT→BS→COP.

Western es solo benchmark y no forma la tasa GSA.

Referido: 3% solo cuando aplica.

Delivery: costo absorbido por GSA.

Corresponsal: 5% sobre el monto efectivamente avanzado.

Compra BS→COP: comisión 0,30%.

Niveles de rentabilidad: 7% recomendada, 5% preferencial, 3% captación y 0% equilibrio.

Utilidad monetaria mínima configurable: 10.000 COP.

Sin dependencia de inventario, CPP, Excel o ERP para pricing.

Archivos nuevos/modificados

bot.py — integración Telegram y flujo /sim CLP→COP V1.

pricing_gsa.py — motor matemático aislado.

test_pricing_gsa.py — pruebas deterministas del motor.

Los demás archivos del repositorio permanecen sin cambios funcionales.

Uso

Guardar una referencia de compra BS→COP:

/bscop 3.35

Ver la referencia actual:

/bscop

Ver la plantilla del simulador:

/simular

Ejemplo CLP→COP:

/sim
TIPO: CLP-COP
MONTO: 100000
CLIENTE: Nombre
METODO: Transferencia
ENTREGA: Transferencia
TASA-BS-COP: 3.35
TASA-CLIENTE: 0
REFERIDO: No
DELIVERY: No
MONTO-DELIVERY: 0
AVANCE-CORRESPONSAL: 0
NOTAS: -

TASA-CLIENTE: 0 usa la tasa recomendada de 7%. Si se ingresa una tasa manual, el Bot evalúa esa tasa y muestra utilidad, rentabilidad, clasificación, benchmark Western y las tasas BS→COP requeridas.

Pruebas

python -m unittest -v test_pricing_gsa.py

La suite V1 incluye los casos de control acordados con la operación de 66.700 CLP / 67.975,49 BS / compra BS→COP 3,35.
