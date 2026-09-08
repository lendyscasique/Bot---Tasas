import unittest

from pricing_gsa import (
    calcular_capacidad_cop,
    evaluar_tasa_clp_cop,
    calcular_bs_cop_requerida,
    calcular_niveles_tasa,
    comparar_western,
)


class TestPricingGSAV1(unittest.TestCase):
    BS = 67975.49
    Q = 3.35
    CLP = 66700

    def setUp(self):
        self.capacidad = calcular_capacidad_cop(self.BS, self.Q)

    def test_capacidad_control(self):
        self.assertAlmostEqual(self.capacidad, 227036.78, places=1)

    def test_operacion_limpia_200k(self):
        tasa = 200000 / self.CLP
        r = evaluar_tasa_clp_cop(self.CLP, tasa, self.capacidad)
        self.assertAlmostEqual(r['utilidad_cop'], 27036.78, places=1)
        self.assertEqual(r['clasificacion'], 'RECOMENDADA')

    def test_referido_200k(self):
        tasa = 200000 / self.CLP
        r = evaluar_tasa_clp_cop(self.CLP, tasa, self.capacidad, referido=True)
        self.assertAlmostEqual(r['comision_referido_cop'], 6000, places=1)
        self.assertAlmostEqual(r['utilidad_cop'], 21036.78, places=1)

    def test_delivery_200k(self):
        tasa = 200000 / self.CLP
        r = evaluar_tasa_clp_cop(self.CLP, tasa, self.capacidad, delivery_cop=5000)
        self.assertAlmostEqual(r['utilidad_cop'], 22036.78, places=1)

    def test_corresponsal_parcial_200k(self):
        tasa = 200000 / self.CLP
        r = evaluar_tasa_clp_cop(self.CLP, tasa, self.capacidad, avance_corresponsal_cop=100000)
        self.assertAlmostEqual(r['comision_corresponsal_cop'], 5000, places=1)
        self.assertAlmostEqual(r['utilidad_cop'], 22036.78, places=1)

    def test_combinado_parcial(self):
        tasa = 200000 / self.CLP
        r = evaluar_tasa_clp_cop(
            self.CLP, tasa, self.capacidad,
            referido=True, delivery_cop=5000, avance_corresponsal_cop=100000,
        )
        self.assertAlmostEqual(r['utilidad_cop'], 11036.78, places=1)
        self.assertAlmostEqual(r['rentabilidad_pct'], 5.5184, places=3)
        self.assertEqual(r['clasificacion'], 'PREFERENCIAL')

    def test_combinado_corresponsal_total_fuera_politica(self):
        tasa = 200000 / self.CLP
        r = evaluar_tasa_clp_cop(
            self.CLP, tasa, self.capacidad,
            referido=True, delivery_cop=5000, avance_corresponsal_cop=200000,
        )
        self.assertAlmostEqual(r['utilidad_cop'], 6036.78, places=1)
        self.assertEqual(r['clasificacion'], 'FUERA_POLITICA')

    def test_tasa_manual_330_referido(self):
        r = evaluar_tasa_clp_cop(self.CLP, 3.30, self.capacidad, referido=True)
        self.assertAlmostEqual(r['utilidad_cop'], 323.48, places=1)
        self.assertEqual(r['clasificacion'], 'FUERA_POLITICA')

    def test_tasa_manual_335_referido_perdida(self):
        r = evaluar_tasa_clp_cop(self.CLP, 3.35, self.capacidad, referido=True)
        self.assertAlmostEqual(r['utilidad_cop'], -3111.57, places=1)
        self.assertEqual(r['clasificacion'], 'PERDIDA')

    def test_motor_inverso_combinado_parcial(self):
        tasa_cliente = 200000 / self.CLP
        q5 = calcular_bs_cop_requerida(
            self.BS, self.CLP, tasa_cliente, 0.05,
            referido=True, delivery_cop=5000, avance_corresponsal_cop=100000,
        )
        self.assertAlmostEqual(q5, 3.3347, places=3)

    def test_niveles(self):
        niveles = calcular_niveles_tasa(self.CLP, self.capacidad)
        self.assertGreater(niveles['captacion']['tasa'], niveles['preferencial']['tasa'])
        self.assertGreater(niveles['preferencial']['tasa'], niveles['recomendada']['tasa'])
        self.assertGreater(niveles['equilibrio']['tasa'], niveles['captacion']['tasa'])

    def test_western_opcional(self):
        self.assertIsNone(comparar_western(self.CLP, 3.20, None))
        comp = comparar_western(self.CLP, 3.20, 3.35)
        self.assertAlmostEqual(comp['brecha_cop'], self.CLP * 0.15, places=1)


if __name__ == '__main__':
    unittest.main()
