#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import pytest

if __name__ == "__main__":
    sys.exit(pytest.main(["-v", "--tb=short", "tests/"]))