import unittest


def fatal_error(**kwargs):
    assert False, "this is fatal error"


class FailMe(unittest.TestCase):
    def test_error(self):
        print("testing")
        fatal_error(a=5, b=6)

    @unittest.skip("why not")
    def test_skip(self):
        print("testing")
        fatal_error(a=5, b=6)
