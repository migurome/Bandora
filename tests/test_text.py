import unittest

from weave.text import norm


class NormTest(unittest.TestCase):
    def test_norm_equivalences(self):
        self.assertEqual(norm("Platero Y Tu"), norm("Platero y tú"))
        self.assertEqual(norm("B.B. King"), norm("B.B.King"))
        self.assertEqual(norm("AC/DC"), "acdc")
        self.assertEqual(norm("Leño"), "leno")
        self.assertEqual(norm("坂本龍一"), "")
        self.assertEqual(norm("Fito y Fitipaldis"), norm("Fito & Fitipaldis"))
        self.assertEqual(norm("Fito & Fitipaldis"), norm("Fito and Fitipaldis"))
        self.assertEqual(norm("Simon&Garfunkel"), norm("Simon and Garfunkel"))
        self.assertEqual(norm("Y"), "y")  # sin palabras a los lados no es conjunción  # sin caracteres latinos: el llamador usa otra clave
