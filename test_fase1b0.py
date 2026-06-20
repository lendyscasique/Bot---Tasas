# ══════════════════════════════════════════════════════════════════════
# FASE 1B.0 — TESTS DE BLINDAJE DEL MOTOR DE INVENTARIO
# GSA Cambios
# ══════════════════════════════════════════════════════════════════════
"""
Tests requeridos explícitamente por el alcance de Fase 1B.0:

    test_id_permanece_constante()
    test_upsert_por_moneda()
    test_unique_constraints()
    test_decimal_no_pierde_precision()
    test_lock_usdt()
    test_concurrencia_usdt()

Estos tests NO requieren conexión real a Supabase para la mayoría de
los casos: se valida el comportamiento de los repositorios, modelos y
locks usando mocks para las llamadas HTTP, de forma que la suite
pueda correr en cualquier entorno (incluyendo CI) sin credenciales.

test_unique_constraints() es la excepción: por su naturaleza, una
constraint UNIQUE solo puede verificarse contra una base de datos
real. Se incluye como test que requiere SUPABASE_URL/SUPABASE_KEY
configuradas, y se omite (skip) explícitamente si no están presentes
-- no se simula, porque simular una constraint de base de datos no
prueba nada real sobre si la migración 002 fue aplicada correctamente.

Ejecutar con:
    python3 -m pytest test_fase1b0.py -v
o sin pytest instalado:
    python3 test_fase1b0.py
"""

import sys
import os
import threading
import time
import unittest
from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))

from modelos_inventario import InventarioActual, MONEDAS_SOPORTADAS
from locks_inventario import obtener_lock, lock_moneda, locks_activos, _locks_por_moneda
import repositorios_inventario as repo_mod
from repositorios_inventario import (
    InventarioActualRepo,
    _DecimalAsStringEncoder,
    _to_json_payload,
)


# ════════════════════════════════════════════════════════════════════
# TEST 1: test_id_permanece_constante
# Valida R1 -- el id de una fila de inventario_actual nunca cambia
# entre el insert inicial y actualizaciones posteriores.
# ════════════════════════════════════════════════════════════════════
class TestIdPermaneceConstante(unittest.TestCase):

    def test_actualizar_nunca_incluye_id_en_payload(self):
        """actualizar() no debe poder enviar 'id' ni por accidente,
        porque la función no lo recibe como parámetro en absoluto."""
        capturado = {}

        def fake_patch(tabla, query, payload):
            capturado["tabla"] = tabla
            capturado["query"] = query
            capturado["payload"] = payload
            return True

        with patch.object(repo_mod, "_patch", side_effect=fake_patch):
            InventarioActualRepo.actualizar(
                moneda="USDT",
                stock_actual=Decimal("150.5"),
                costo_promedio=Decimal("101.67"),
            )

        self.assertNotIn("id", capturado["payload"],
            "actualizar() jamás debe incluir 'id' en el payload del PATCH")
        self.assertEqual(capturado["query"], "moneda=eq.USDT",
            "actualizar() debe identificar la fila por moneda, no por id")
        print("✅ test_actualizar_nunca_incluye_id_en_payload PASÓ")

    def test_crear_solo_se_ejecuta_si_la_moneda_no_existe(self):
        """crear() debe rechazar silenciosamente (retornar False) si
        ya existe una fila para esa moneda, sin sobrescribir nada."""
        fila_existente = InventarioActual(
            moneda="USDT", stock_actual=Decimal("10"), costo_promedio=Decimal("100")
        )

        with patch.object(InventarioActualRepo, "obtener", return_value=fila_existente):
            with patch.object(repo_mod, "_post") as mock_post:
                resultado = InventarioActualRepo.crear(
                    InventarioActual(moneda="USDT", stock_actual=Decimal("999"))
                )

        self.assertFalse(resultado, "crear() debe retornar False si la moneda ya existe")
        mock_post.assert_not_called()
        print("✅ test_crear_solo_se_ejecuta_si_la_moneda_no_existe PASÓ")

    def test_id_original_no_se_pierde_en_ciclo_crear_actualizar(self):
        """Simula: crear() una vez (genera id X) -> actualizar() varias
        veces -> el id X nunca debe aparecer como sobrescrito porque
        actualizar() no lo toca en absoluto."""
        inv = InventarioActual(moneda="COP", stock_actual=Decimal("1000"))
        id_original = inv.id

        capturados = []

        def fake_patch(tabla, query, payload):
            capturados.append(payload)
            return True

        with patch.object(repo_mod, "_patch", side_effect=fake_patch):
            for i in range(5):
                InventarioActualRepo.actualizar(
                    moneda="COP", stock_actual=Decimal(str(1000 + i))
                )

        for payload in capturados:
            self.assertNotIn("id", payload)

        # El id original del objeto en memoria tampoco cambió,
        # porque actualizar() ni siquiera recibe el objeto InventarioActual
        self.assertEqual(inv.id, id_original)
        print("✅ test_id_original_no_se_pierde_en_ciclo_crear_actualizar PASÓ")


# ════════════════════════════════════════════════════════════════════
# TEST 2: test_upsert_por_moneda
# ════════════════════════════════════════════════════════════════════
class TestUpsertPorMoneda(unittest.TestCase):

    def test_upsert_crea_si_no_existe(self):
        with patch.object(InventarioActualRepo, "obtener", return_value=None):
            with patch.object(repo_mod, "_post", return_value=[{"ok": True}]) as mock_post:
                resultado = InventarioActualRepo.upsert_por_moneda(
                    moneda="CLP", stock_actual=Decimal("500")
                )
        self.assertTrue(resultado)
        mock_post.assert_called_once()
        print("✅ test_upsert_crea_si_no_existe PASÓ")

    def test_upsert_actualiza_si_ya_existe_sin_tocar_id(self):
        fila_existente = InventarioActual(
            moneda="CLP", stock_actual=Decimal("500"), costo_promedio=Decimal("900")
        )
        capturado = {}

        def fake_patch(tabla, query, payload):
            capturado["payload"] = payload
            return True

        with patch.object(InventarioActualRepo, "obtener", return_value=fila_existente):
            with patch.object(repo_mod, "_patch", side_effect=fake_patch) as mock_patch:
                with patch.object(repo_mod, "_post") as mock_post:
                    resultado = InventarioActualRepo.upsert_por_moneda(
                        moneda="CLP", stock_actual=Decimal("750")
                    )

        self.assertTrue(resultado)
        mock_post.assert_not_called()
        mock_patch.assert_called_once()
        self.assertNotIn("id", capturado["payload"])
        print("✅ test_upsert_actualiza_si_ya_existe_sin_tocar_id PASÓ")

    def test_upsert_sin_cambios_retorna_true_sin_llamar_red(self):
        fila_existente = InventarioActual(moneda="USD", stock_actual=Decimal("10"))
        with patch.object(InventarioActualRepo, "obtener", return_value=fila_existente):
            with patch.object(repo_mod, "_patch") as mock_patch:
                with patch.object(repo_mod, "_post") as mock_post:
                    resultado = InventarioActualRepo.upsert_por_moneda(moneda="USD")
        self.assertTrue(resultado)
        mock_patch.assert_not_called()
        mock_post.assert_not_called()
        print("✅ test_upsert_sin_cambios_retorna_true_sin_llamar_red PASÓ")


# ════════════════════════════════════════════════════════════════════
# TEST 3: test_unique_constraints
# Requiere base de datos real -- se omite si no hay credenciales.
# ════════════════════════════════════════════════════════════════════
class TestUniqueConstraints(unittest.TestCase):

    @unittest.skipUnless(
        os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"),
        "Requiere SUPABASE_URL y SUPABASE_KEY reales para validar "
        "constraints contra la base de datos -- no se simula."
    )
    def test_inventario_movimientos_rechaza_duplicado(self):
        """Inserta el mismo movimiento dos veces; la segunda debe
        fallar por la UNIQUE constraint de la migración 002."""
        import requests as real_requests
        from modelos_inventario import InventarioMovimiento
        from repositorios_inventario import InventarioMovimientosRepo

        ref_test = f"TEST_UNIQUE_{int(time.time())}"
        mov = InventarioMovimiento(
            fecha=date.today(),
            moneda="USDT",
            tipo_movimiento="TEST_AUDITORIA",
            entrada=Decimal("1"),
            referencia_operacion=ref_test,
        )

        primer_insert = InventarioMovimientosRepo.insertar(mov)
        self.assertTrue(primer_insert, "El primer insert debe tener éxito")

        # Mismo referencia_operacion + moneda + tipo_movimiento -> debe rechazar
        segundo_insert = InventarioMovimientosRepo.insertar(mov)
        self.assertFalse(segundo_insert,
            "El segundo insert idéntico debe ser rechazado por la UNIQUE constraint")

        print("✅ test_inventario_movimientos_rechaza_duplicado PASÓ (contra BD real)")

    def test_unique_constraints_skip_explicito_sin_credenciales(self):
        """Si no hay credenciales, este test deja constancia explícita
        de que la verificación real de constraints NO se ejecutó --
        en vez de fallar silenciosamente o dar falso positivo."""
        if not (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY")):
            print(
                "⚠️ test_unique_constraints: SIN credenciales Supabase, "
                "la validación real de constraints NO se ejecutó en este run. "
                "Ejecutar con SUPABASE_URL/SUPABASE_KEY configuradas para "
                "una verificación completa contra la base de datos."
            )
        self.assertTrue(True)


# ════════════════════════════════════════════════════════════════════
# TEST 4: test_decimal_no_pierde_precision
# Valida R6 -- la serialización preserva precisión decimal exacta.
# ════════════════════════════════════════════════════════════════════
class TestDecimalNoPierdePrecision(unittest.TestCase):

    def test_decimal_se_serializa_como_string_no_float(self):
        valor = Decimal("101.67000001")
        payload = {"costo_promedio": valor}
        json_str = _to_json_payload(payload)

        self.assertIn('"101.67000001"', json_str,
            "El Decimal debe aparecer como STRING en el JSON, no como número binario float")
        self.assertNotIn("101.67000000999", json_str,
            "No debe haber artefactos de redondeo de float en el JSON")
        print(f"✅ test_decimal_se_serializa_como_string_no_float PASÓ — JSON: {json_str}")

    def test_decimal_con_8_decimales_no_se_trunca(self):
        """NUMERIC(18,8) permite hasta 8 decimales -- confirmar que
        ninguno se pierde en la serialización."""
        valor = Decimal("0.00000001")  # el decimal más pequeño representable
        payload = {"stock_actual": valor}
        json_str = _to_json_payload(payload)

        self.assertIn('"0.00000001"', json_str)
        print(f"✅ test_decimal_con_8_decimales_no_se_trunca PASÓ — JSON: {json_str}")

    def test_float_hubiera_perdido_precision_aqui(self):
        """Test de control: demuestra que el problema que R6 corrige
        es real, comparando contra el comportamiento de float()."""
        valor_decimal = Decimal("101.67")
        valor_float = float(valor_decimal)

        # Esta es la prueba de que el riesgo R6 era real:
        # repr(float) puede no coincidir exactamente con el Decimal original
        recuperado_de_decimal = str(valor_decimal)
        recuperado_de_float = repr(valor_float)

        self.assertEqual(recuperado_de_decimal, "101.67")
        # No afirmamos que float SIEMPRE falle (101.67 es uno de los casos
        # que float representa razonablemente bien), pero confirmamos
        # que nuestra serialización usa el camino Decimal->string, no
        # Decimal->float->json, evitando la clase de error que motivó R6.
        json_decimal = _to_json_payload({"v": valor_decimal})
        self.assertIn('"101.67"', json_decimal)
        print("✅ test_float_hubiera_perdido_precision_aqui PASÓ (camino Decimal->str confirmado)")

    def test_lista_de_decimales_en_batch_insert(self):
        """Confirma que _to_json_payload también preserva precisión
        cuando el payload es una lista (caso de insertar_lote())."""
        payload = [
            {"entrada": Decimal("50.12345678")},
            {"salida": Decimal("25.87654321")},
        ]
        json_str = _to_json_payload(payload)
        self.assertIn('"50.12345678"', json_str)
        self.assertIn('"25.87654321"', json_str)
        print("✅ test_lista_de_decimales_en_batch_insert PASÓ")


# ════════════════════════════════════════════════════════════════════
# TEST 5: test_lock_usdt
# Valida R2 (parte 1) -- existe un lock independiente por moneda.
# ════════════════════════════════════════════════════════════════════
class TestLockUSDT(unittest.TestCase):

    def test_obtener_lock_usdt_retorna_lock_valido(self):
        lock = obtener_lock("USDT")
        self.assertIsInstance(lock, type(threading.Lock()))
        print("✅ test_obtener_lock_usdt_retorna_lock_valido PASÓ")

    def test_obtener_lock_siempre_retorna_el_mismo_objeto(self):
        """Crítico: si cada llamada creara un Lock nuevo, la exclusión
        mutua sería una ilusión -- dos hilos tendrían locks distintos
        y nunca se bloquearían entre sí realmente."""
        lock1 = obtener_lock("USDT")
        lock2 = obtener_lock("USDT")
        self.assertIs(lock1, lock2,
            "obtener_lock() debe retornar SIEMPRE el mismo objeto Lock para la misma moneda")
        print("✅ test_obtener_lock_siempre_retorna_el_mismo_objeto PASÓ")

    def test_cada_moneda_tiene_lock_independiente(self):
        lock_usdt = obtener_lock("USDT")
        lock_cop = obtener_lock("COP")
        self.assertIsNot(lock_usdt, lock_cop,
            "USDT y COP deben tener locks DISTINTOS e independientes")
        print("✅ test_cada_moneda_tiene_lock_independiente PASÓ")

    def test_todas_las_monedas_soportadas_tienen_lock_preregistrado(self):
        for moneda in MONEDAS_SOPORTADAS:
            self.assertIn(moneda, _locks_por_moneda,
                f"La moneda '{moneda}' debe tener su lock pre-creado al importar el módulo")
        print("✅ test_todas_las_monedas_soportadas_tienen_lock_preregistrado PASÓ")

    def test_lock_moneda_context_manager_libera_correctamente(self):
        with lock_moneda("USDT"):
            self.assertTrue(obtener_lock("USDT").locked())
        self.assertFalse(obtener_lock("USDT").locked(),
            "El lock debe liberarse automáticamente al salir del 'with'")
        print("✅ test_lock_moneda_context_manager_libera_correctamente PASÓ")

    def test_lock_moneda_libera_incluso_si_hay_excepcion(self):
        try:
            with lock_moneda("CLP"):
                raise ValueError("error simulado dentro del bloque crítico")
        except ValueError:
            pass
        self.assertFalse(obtener_lock("CLP").locked(),
            "El lock debe liberarse aunque ocurra una excepción dentro del 'with'")
        print("✅ test_lock_moneda_libera_incluso_si_hay_excepcion PASÓ")


# ════════════════════════════════════════════════════════════════════
# TEST 6: test_concurrencia_usdt
# Valida R2 (parte 2) -- exclusión mutua real bajo dos hilos.
# ════════════════════════════════════════════════════════════════════
class TestConcurrenciaUSDT(unittest.TestCase):

    def test_dos_hilos_no_entran_simultaneamente_a_seccion_critica(self):
        """
        Simula dos hilos intentando "operar" sobre USDT al mismo
        tiempo. Sin el lock, ambos podrían entrar a la sección
        crítica simultáneamente. Con el lock, se garantiza que
        solo uno esté dentro en cualquier instante.

        Mecanismo de verificación: un contador compartido que se
        incrementa al entrar y decrementa al salir de la sección
        crítica. Si en algún momento el contador supera 1, hubo
        una violación de exclusión mutua.
        """
        contador_dentro = {"valor": 0}
        max_simultaneos = {"valor": 0}
        lock_contador = threading.Lock()  # solo para proteger el contador de prueba
        violacion_detectada = {"flag": False}

        def trabajo_critico(id_hilo, resultados):
            with lock_moneda("USDT"):
                with lock_contador:
                    contador_dentro["valor"] += 1
                    if contador_dentro["valor"] > max_simultaneos["valor"]:
                        max_simultaneos["valor"] = contador_dentro["valor"]
                    if contador_dentro["valor"] > 1:
                        violacion_detectada["flag"] = True

                # Simula trabajo que toma tiempo (la ventana donde
                # una condición de carrera real causaría daño)
                time.sleep(0.05)

                with lock_contador:
                    contador_dentro["valor"] -= 1

                resultados.append(id_hilo)

        resultados = []
        hilo1 = threading.Thread(target=trabajo_critico, args=(1, resultados))
        hilo2 = threading.Thread(target=trabajo_critico, args=(2, resultados))

        inicio = time.time()
        hilo1.start()
        hilo2.start()
        hilo1.join(timeout=5)
        hilo2.join(timeout=5)
        duracion = time.time() - inicio

        self.assertFalse(violacion_detectada["flag"],
            "Se detectaron DOS hilos dentro de la sección crítica de USDT "
            "AL MISMO TIEMPO -- el lock no está garantizando exclusión mutua")
        self.assertEqual(max_simultaneos["valor"], 1,
            "El máximo de hilos simultáneos dentro de la sección crítica debe ser 1")
        self.assertEqual(len(resultados), 2, "Ambos hilos deben completar su trabajo")
        # Si el lock funciona, el trabajo se serializa: el tiempo total
        # debe ser cercano a 2x0.05s=0.1s, no a 0.05s (que indicaría
        # que ambos corrieron en paralelo sin bloquearse).
        self.assertGreaterEqual(duracion, 0.09,
            "La duración sugiere que los hilos NO se serializaron como se esperaba")

        print(
            f"✅ test_dos_hilos_no_entran_simultaneamente_a_seccion_critica PASÓ "
            f"(máx simultáneos={max_simultaneos['valor']}, duración={duracion:.3f}s)"
        )

    def test_hilos_en_monedas_distintas_no_se_bloquean_entre_si(self):
        """Confirma que el lock es POR MONEDA: una operación sobre
        CLP no debe esperar a que termine una operación sobre USDT."""
        eventos = []
        lock_eventos = threading.Lock()

        def trabajo(moneda, duracion):
            with lock_moneda(moneda):
                with lock_eventos:
                    eventos.append(("entra", moneda, time.time()))
                time.sleep(duracion)
                with lock_eventos:
                    eventos.append(("sale", moneda, time.time()))

        hilo_usdt = threading.Thread(target=trabajo, args=("USDT", 0.1))
        hilo_clp = threading.Thread(target=trabajo, args=("CLP", 0.1))

        inicio = time.time()
        hilo_usdt.start()
        hilo_clp.start()
        hilo_usdt.join(timeout=5)
        hilo_clp.join(timeout=5)
        duracion_total = time.time() - inicio

        # Si se bloquearan entre sí (incorrectamente), tomaría ~0.2s.
        # Como son monedas distintas, deben correr en paralelo: ~0.1s.
        self.assertLess(duracion_total, 0.18,
            "Monedas distintas no deberían bloquearse entre sí -- "
            "la duración sugiere serialización incorrecta entre USDT y CLP")

        print(
            f"✅ test_hilos_en_monedas_distintas_no_se_bloquean_entre_si PASÓ "
            f"(duración total={duracion_total:.3f}s, esperado cercano a 0.1s)"
        )

    def test_concurrencia_real_sobre_inventario_actual_repo(self):
        """
        Test de integración (con mock de red): simula 10 hilos
        intentando actualizar() el stock de USDT simultáneamente,
        y confirma que las 10 escrituras se completan sin error y
        sin que ninguna se pierda silenciosamente -- el lock fuerza
        que ocurran una tras otra.

        IMPORTANTE sobre el diseño de este test: el parche de
        repo_mod._patch se aplica UNA SOLA VEZ, fuera de los hilos
        y antes de lanzarlos. unittest.mock.patch.object() no es
        seguro para aplicarse concurrentemente desde varios hilos
        sobre el mismo atributo (cada hilo haría su propio
        __enter__/__exit__, y uno puede restaurar el valor original
        mientras otro todavía lo necesita parcheado -- esto es un
        problema del mecanismo de mocking, no del código bajo
        prueba). La forma correcta de testear concurrencia con
        mocks es parchear antes de crear los hilos.
        """
        escrituras_registradas = []
        lock_registro = threading.Lock()

        def fake_patch(tabla, query, payload):
            time.sleep(0.01)
            with lock_registro:
                escrituras_registradas.append(payload.get("stock_actual"))
            return True

        def hacer_actualizacion(valor):
            InventarioActualRepo.actualizar(moneda="USDT", stock_actual=Decimal(str(valor)))

        with patch.object(repo_mod, "_patch", side_effect=fake_patch):
            hilos = [threading.Thread(target=hacer_actualizacion, args=(i,)) for i in range(10)]
            for h in hilos:
                h.start()
            for h in hilos:
                h.join(timeout=10)

        self.assertEqual(len(escrituras_registradas), 10,
            "Las 10 actualizaciones concurrentes deben completarse, "
            "ninguna debe perderse por condición de carrera")
        print(
            f"✅ test_concurrencia_real_sobre_inventario_actual_repo PASÓ "
            f"(10/10 escrituras completadas: {sorted(escrituras_registradas, key=str)})"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
