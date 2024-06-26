# Copyright (C) 2017-2024 by Daniel Shapero <shapero@uw.edu> and David
# Lilien
#
# This file is part of icepack.
#
# icepack is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# The full text of the license can be found in the file LICENSE in the
# icepack source directory or at <http://www.gnu.org/licenses/>.

import pytest
import numpy as np
import rasterio
import xarray
import firedrake
from firedrake import dx
import icepack


def test_interpolating_function():
    nx, ny = 32, 32
    mesh = firedrake.UnitSquareMesh(nx, ny)
    x = firedrake.SpatialCoordinate(mesh)
    Q = firedrake.FunctionSpace(mesh, "CG", 2)
    q = icepack.interpolate(x[0] ** 2 - x[1] ** 2, Q)
    assert abs(firedrake.assemble(q * dx)) < 1e-6


def make_rio_dataset(array, missing=-9999.0):
    ny = array.shape[0] - 1
    nx = array.shape[1] - 1
    transform = rasterio.transform.from_origin(
        west=0.0, north=1.0, xsize=1 / nx, ysize=1 / ny
    )

    memfile = rasterio.MemoryFile(ext=".tif")
    opts = {
        "driver": "GTiff",
        "count": 1,
        "width": nx + 1,
        "height": ny + 1,
        "dtype": array.dtype,
        "transform": transform,
        "nodata": missing,
    }

    with memfile.open(**opts) as dataset:
        dataset.write(array, indexes=1)
    return memfile.open()


def make_xarray_dataset(array, missing=-9999.0):
    ny = array.shape[0]
    nx = array.shape[1]
    x = np.linspace(0.0, 1.0, nx)
    y = np.linspace(0.0, 1.0, ny)
    return xarray.DataArray(array, coords=[y, x], dims=["y", "x"])


def make_dataset(array, missing, package):
    if package == "rasterio":
        return make_rio_dataset(np.flipud(array), missing)
    if package == "xarray":
        return make_xarray_dataset(array, missing)
    raise ValueError("Package must be either `rasterio` or `xarray`!")


def make_domain(nx, ny, xmin, ymin, width, height):
    mesh = firedrake.UnitSquareMesh(nx, ny, diagonal="crossed")
    x, y = firedrake.SpatialCoordinate(mesh)
    Vc = mesh.coordinates.function_space()
    expr = firedrake.as_vector((width * x + xmin, height * y + ymin))
    f = firedrake.Function(Vc).interpolate(expr)
    mesh.coordinates.assign(f)
    return mesh


@pytest.mark.parametrize("package", ("rasterio", "xarray"))
def test_interpolating_scalar_field(package):
    n = 32
    array = np.array([[(i + j) / n for j in range(n + 1)] for i in range(n + 1)])
    missing = -9999.0
    array[0, 0] = missing
    dataset = make_dataset(array, missing, package)

    mesh = make_domain(48, 48, xmin=1 / 4, ymin=1 / 4, width=1 / 2, height=1 / 2)
    x, y = firedrake.SpatialCoordinate(mesh)
    Q = firedrake.FunctionSpace(mesh, "CG", 1)
    p = firedrake.Function(Q).interpolate(x + y)
    q = icepack.interpolate(dataset, Q)

    assert firedrake.norm(p - q) / firedrake.norm(p) < 1e-10


@pytest.mark.parametrize("package", ("rasterio", "xarray"))
def test_interpolating_scalar_field_3d(package):
    n = 32
    array = np.array([[(i + j) / n for j in range(n + 1)] for i in range(n + 1)])
    missing = -9999.0
    array[0, 0] = missing
    dataset = make_dataset(array, missing, package)

    mesh2d = make_domain(48, 48, xmin=1 / 4, ymin=1 / 4, width=1 / 2, height=1 / 2)
    mesh = firedrake.ExtrudedMesh(mesh2d, layers=1)

    x, y, z = firedrake.SpatialCoordinate(mesh)
    Q = firedrake.FunctionSpace(mesh, "CG", 1, vfamily="R", vdegree=0)
    p = firedrake.Function(Q).interpolate(x + y)
    q = icepack.interpolate(dataset, Q)

    assert firedrake.norm(p - q) / firedrake.norm(p) < 1e-10


@pytest.mark.parametrize("package", ("rasterio", "xarray"))
def test_nearest_neighbor_interpolation(package):
    n = 32
    array = np.array([[(i + j) / n for j in range(n + 1)] for i in range(n + 1)])
    missing = -9999.0
    array[0, 0] = missing
    dataset = make_dataset(array, missing, package)

    mesh = make_domain(48, 48, xmin=1 / 4, ymin=1 / 4, width=1 / 2, height=1 / 2)
    x, y = firedrake.SpatialCoordinate(mesh)
    Q = firedrake.FunctionSpace(mesh, "CG", 1)
    p = firedrake.Function(Q).interpolate(x + y)
    q = icepack.interpolate(dataset, Q, method="nearest")

    relative_error = firedrake.norm(p - q) / firedrake.norm(p)
    assert (relative_error > 1e-10) and (relative_error < 1 / n)


@pytest.mark.parametrize("package", ("rasterio", "xarray"))
def test_interpolating_vector_field(package):
    n = 32
    array_vx = np.array([[(i + j) / n for j in range(n + 1)] for i in range(n + 1)])
    missing = -9999.0
    array_vx[0, 0] = missing

    array_vy = np.array([[(j - i) / n for j in range(n + 1)] for i in range(n + 1)])
    array_vy[-1, -1] = -9999.0

    vx = make_dataset(array_vx, missing, package)
    vy = make_dataset(array_vy, missing, package)

    mesh = make_domain(48, 48, xmin=1 / 4, ymin=1 / 4, width=1 / 2, height=1 / 2)
    x, y = firedrake.SpatialCoordinate(mesh)
    V = firedrake.VectorFunctionSpace(mesh, "CG", 1)
    u = firedrake.Function(V).interpolate(firedrake.as_vector((x + y, x - y)))
    v = icepack.interpolate((vx, vy), V)

    assert firedrake.norm(u - v) / firedrake.norm(u) < 1e-10


@pytest.mark.parametrize("package", ("rasterio", "xarray"))
def test_interpolating_vector_field_3d(package):
    n = 32
    array_vx = np.array([[(i + j) / n for j in range(n + 1)] for i in range(n + 1)])
    missing = -9999.0
    array_vx[0, 0] = missing

    array_vy = np.array([[(j - i) / n for j in range(n + 1)] for i in range(n + 1)])
    array_vy[-1, -1] = -9999.0

    vx = make_dataset(array_vx, missing, package)
    vy = make_dataset(array_vy, missing, package)

    mesh2d = make_domain(48, 48, xmin=1 / 4, ymin=1 / 4, width=1 / 2, height=1 / 2)
    mesh = firedrake.ExtrudedMesh(mesh2d, layers=1)

    x, y, z = firedrake.SpatialCoordinate(mesh)
    V = firedrake.VectorFunctionSpace(mesh, "CG", 1, dim=2, vfamily="GL", vdegree=2)
    u = firedrake.Function(V).interpolate(firedrake.as_vector((x + y, x - y)))
    v = icepack.interpolate((vx, vy), V)

    assert firedrake.norm(u - v) / firedrake.norm(u) < 1e-10


@pytest.mark.parametrize("package", ("rasterio", "xarray"))
def test_close_to_edge(package):
    n = 32
    array = np.array([[(i + j) / n for j in range(n + 1)] for i in range(n + 1)])
    missing = -9999.0
    dataset = make_dataset(array, missing, package)

    xmin, ymin = 1 / (2 * n), 3 / (4 * n)
    mesh = make_domain(48, 48, xmin=xmin, ymin=ymin, width=1 / 2, height=1 / 2)
    Q = firedrake.FunctionSpace(mesh, "CG", 1)
    q = icepack.interpolate(dataset, Q)
