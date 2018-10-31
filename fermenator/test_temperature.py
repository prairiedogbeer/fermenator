import unittest
import mock

from .temperature import *
from .exception import ConfigurationError

# These three values should all be an equal temperature.
# Keep in mind that decimal precision plays a role, so choose
# a value that converts nicely, like 0C/32F/273.15K
CELCIUS_VAL = 0.0
FAHRENHEIT_VAL = 32.0
KELVIN_VAL = 273.15

class TestTempConversions(unittest.TestCase):
    def setUp(self):
        pass

    def test_degrees_c_to_k(self):
        self.assertEqual(
            degrees_c_to_k(CELCIUS_VAL), KELVIN_VAL)

    def test_degrees_k_to_c(self):
        self.assertEqual(
            degrees_k_to_c(KELVIN_VAL), CELCIUS_VAL)

    def test_degrees_f_to_c(self):
        self.assertEqual(
            degrees_f_to_c(FAHRENHEIT_VAL), CELCIUS_VAL)

    def test_degrees_c_to_f(self):
        self.assertEqual(
            degrees_c_to_f(CELCIUS_VAL), FAHRENHEIT_VAL)

    def test_degrees_f_to_k(self):
        self.assertEqual(
            degrees_f_to_k(FAHRENHEIT_VAL), KELVIN_VAL)

    def test_degrees_k_to_f(self):
        self.assertEqual(
            degrees_k_to_f(KELVIN_VAL), FAHRENHEIT_VAL)

class TestTemperature(unittest.TestCase):
    def test___init__(self):
        with self.assertRaises(ConfigurationError):
            Temperature(1414.0, 'h')
        # check case insensivity
        self.assertEqual(
            Temperature(CELCIUS_VAL, 'C').as_c(),
            Temperature(CELCIUS_VAL, 'c').as_c())
        self.assertEqual(
            Temperature(FAHRENHEIT_VAL, 'F').as_c(),
            Temperature(FAHRENHEIT_VAL, 'f').as_c())
        self.assertEqual(
            Temperature(KELVIN_VAL, 'K').as_c(),
            Temperature(KELVIN_VAL, 'k').as_c())

    def test_from_celcius(self):
        temp = Temperature.from_celcius(CELCIUS_VAL)
        self.assertEqual(CELCIUS_VAL, temp.as_c())

    def test_from_fahrenheit(self):
        temp = Temperature.from_fahrenheit(FAHRENHEIT_VAL)
        self.assertEqual(FAHRENHEIT_VAL, temp.as_f())

    def test_from_kelvin(self):
        temp = Temperature.from_kelvin(KELVIN_VAL)
        self.assertEqual(KELVIN_VAL, temp.as_k())

    def test_as_unit(self):
        temp = Temperature.from_celcius(CELCIUS_VAL)
        self.assertEqual(temp.as_c(), CELCIUS_VAL)
        self.assertEqual(temp.as_k(), KELVIN_VAL)
        self.assertEqual(temp.as_f(), FAHRENHEIT_VAL)
        with self.assertRaises(ConfigurationError):
            temp.as_unit('P')

    def test___add__(self):
        temp1 = Temperature.from_celcius(CELCIUS_VAL)
        temp2 = Temperature.from_celcius(CELCIUS_VAL)
        tempsum = temp1 + temp2
        self.assertIsInstance(tempsum, Temperature)
        self.assertEqual(tempsum.as_k(), KELVIN_VAL * 2)

    def test__iadd__(self):
        temp1 = Temperature.from_celcius(CELCIUS_VAL)
        foo = temp1
        temp2 = Temperature.from_celcius(CELCIUS_VAL)
        temp1 += temp2
        self.assertIs(foo, temp1)
        self.assertIsInstance(temp1, Temperature)
        self.assertEqual(temp1.as_k(), KELVIN_VAL * 2)

    def test___sub__(self):
        temp1 = Temperature.from_kelvin(KELVIN_VAL)
        temp2 = Temperature.from_kelvin(KELVIN_VAL)
        temp3 = temp1 - temp2
        self.assertIsInstance(temp3, Temperature)
        self.assertEqual(temp3.as_k(), 0.0)

    def test___mul__(self):
        temp1 = Temperature.from_kelvin(KELVIN_VAL)
        temp2 = Temperature.from_kelvin(KELVIN_VAL)
        temp3 = temp1 * temp2
        self.assertIsInstance(temp3, Temperature)
        self.assertEqual(temp3.as_k(), KELVIN_VAL * KELVIN_VAL)
        temp4 = temp1 * 2
        self.assertIsInstance(temp4, Temperature)
        self.assertEqual(temp4.as_k(), KELVIN_VAL * 2)

    def test___div__(self):
        temp1 = Temperature.from_kelvin(KELVIN_VAL)
        temp2 = Temperature.from_kelvin(KELVIN_VAL)
        temp3 = temp1 / temp2
        self.assertIsInstance(temp3, Temperature)
        self.assertEqual(temp3.as_k(), 1.0)
        temp4 = temp1 / KELVIN_VAL
        self.assertIsInstance(temp4, Temperature)
        self.assertEqual(temp4.as_k(), 1.0)

    def test___str__(self):
        temp = Temperature.from_kelvin(KELVIN_VAL)
        self.assertEqual(str(temp), "{:.2f} K".format(KELVIN_VAL))
