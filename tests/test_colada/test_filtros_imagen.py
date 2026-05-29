# -*- coding: utf-8 -*-
import numpy as np
import pytest
from arqueo_cid.colada.core.filtros_imagen import (
    sobel, laplace, gaussian, median_filter, canny
)

def test_sobel():
    arr = np.random.rand(32, 32).astype(np.float32)
    out = sobel(arr)
    assert out.shape == arr.shape
    assert out.dtype == np.float32

def test_laplace():
    arr = np.random.rand(32, 32).astype(np.float32)
    out = laplace(arr)
    assert out.shape == arr.shape

def test_gaussian():
    arr = np.random.rand(32, 32).astype(np.float32)
    out = gaussian(arr, sigma=1.0)
    assert out.shape == arr.shape

def test_median_filter():
    arr = np.random.rand(32, 32).astype(np.float32)
    out = median_filter(arr, size=3)
    assert out.shape == arr.shape
    out2 = median_filter(arr, size=4)  # debe ajustarse a impar
    assert out2.shape == arr.shape

def test_canny():
    arr = np.random.rand(32, 32).astype(np.float32)
    out = canny(arr, sigma=1.0, low=0.1, high=0.2)
    assert out.shape == arr.shape
    assert np.all((out == 0) | (out == 1) | (out == 2))