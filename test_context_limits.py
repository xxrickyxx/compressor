import unittest
from context_limits import validate_context,generation_budget

class Tests(unittest.TestCase):
    def test_bounds_and_types(self):
        for value in (128,512,1024,8192): self.assertEqual(validate_context(value),value)
        for value in (True,127,8193,1024.0,'1024'):
            with self.assertRaises(ValueError): validate_context(value)
        with self.assertRaises(ValueError): validate_context(2048,1024)
    def test_prompt_and_output_share_budget(self):
        self.assertEqual(generation_budget(700,128,1024),128)
        self.assertEqual(generation_budget(1000,128,1024),24)
        self.assertEqual(generation_budget(127,128,128),1)
        with self.assertRaises(ValueError): generation_budget(1024,48,1024)
        with self.assertRaises(ValueError): generation_budget(700,48,512)

if __name__=='__main__': unittest.main()
