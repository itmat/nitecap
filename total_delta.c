#include <Python.h>
#include <numpy/arrayobject.h>
#include <math.h>

static PyObject* sum_abs_differences(PyObject *dummy, PyObject *args) {

    PyObject *in_object = NULL;
    PyObject *out_object = NULL;
    PyArrayObject *in_array = NULL;
    PyArrayObject *out_array = NULL;

    npy_intp *dims;

    double sum=0.0;

    if (!PyArg_ParseTuple(args, "OO", &in_object, &out_object)) {
        return NULL;
    }

    // Convert Numpy array to be c-contiguous (if necessary) so that we can read from it
    in_array = (PyArrayObject*) PyArray_FROM_OTF(in_object, NPY_DOUBLE, NPY_ARRAY_IN_ARRAY);
    if (in_array == NULL) {
        return NULL;
    }

    // Convert output array to be c-contiguous and so that we can output to it
    out_array = (PyArrayObject*) PyArray_FROM_OTF(out_object, NPY_DOUBLE, NPY_ARRAY_INOUT_ARRAY2);
    if (out_array == NULL) {
        goto fail;
    }

    /* Get and verify dimensions and sizes of the arrays */
    if (in_array->nd != 4) {
        PyErr_SetString(PyExc_IndexError, "input array needs to be 4-dimensional");
        goto fail;
    }

    if (out_array->nd != 2) {
        PyErr_SetString(PyExc_IndexError, "output array needs to be 2-dimensional");
        goto fail;
    }

    if ((out_array->dimensions[0] != in_array->dimensions[0]) || (out_array->dimensions[1] != in_array->dimensions[3])) {
        PyErr_SetString(PyExc_IndexError, "output array must have a compatible shape with input array");
        goto fail;
    }

    dims = in_array->dimensions;

    /* Perform the computation */
    /* Compute the sum of absolute differences of all combinations of
     * reps from one timepoint with the reps of the next timepoint
     *
     * Recall that the first dimension of input array gives the permutations
     * The second is timepoints, the third is replicates, and fourth is genes
     */
    for(npy_intp perm = 0; perm < dims[0]; ++perm) {
        for(npy_intp gene = 0; gene < dims[3]; ++gene) {
            sum = 0.0;
            for(npy_intp timepoint = 0; timepoint < dims[1]; ++timepoint) {
                /* Now take two different replicates */
                for(npy_intp rep = 0; rep < dims[2]; ++rep) {
                    for(npy_intp rep2 = 0; rep2 < dims[2]; ++rep2) {
                        npy_intp timepoint_next = (timepoint+1) % dims[1];
                        double a = *(double*)PyArray_GETPTR4(in_array, perm, timepoint, rep, gene);
                        double b = *(double*)PyArray_GETPTR4(in_array, perm, timepoint_next, rep2, gene);

                        double abs_diff = fabs(a-b);
                        if (abs_diff == abs_diff) {
                            /* This checks whether abs_diff is non-NaN. If NaN, just skip it. */
                            sum += abs_diff;
                        }
                    }
                }
            }
            double *out = (double*) PyArray_GETPTR2(out_array, perm, gene);
            *out = sum;
        }
    }
    
    /* Cleanup memory */
    Py_XDECREF(in_array);
    PyArray_ResolveWritebackIfCopy(out_array);
    Py_XDECREF(out_array);

    Py_INCREF(Py_None);
    return Py_None;

    fail:
        /* An error occured, so cleanup and quit */
        Py_XDECREF(in_array);
        PyArray_DiscardWritebackIfCopy(out_array);
        Py_XDECREF(out_array);

        return NULL;
}

/* Boiler plate to create module and export the function */

static PyMethodDef total_delta_methods[] = {
    {"sum_abs_differences", sum_abs_differences, METH_VARARGS,
        "Sum the absolute value of the differences of all possible choices of replicate at one timepoint with replicates at adjacent timepoints."}, 
    {NULL, NULL, 0, NULL} /* SENTINEL */
};

static struct PyModuleDef cPyModuleDef = {
    PyModuleDef_HEAD_INIT,
    "total_delta",
    "Computational backend for nitecap",
    -1,
    total_delta_methods
};

PyMODINIT_FUNC
PyInit_total_delta(void){
    import_array(); /* Necessary for Numpy usage */
    return PyModule_Create(&cPyModuleDef);
}
