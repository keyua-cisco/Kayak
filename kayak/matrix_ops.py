# Author: Ryan P. Adams <rpa@seas.harvard.edu>
# Copyright 2014, The President and Fellows of Harvard University

import numpy as np

from .        import Differentiable
from util     import broadcast

class MatMult(Differentiable):

    def __init__(self, A, B, *args):
        # Recurse to handle lists of arguments.
        if len(args) > 0:
            B = MatMult(B, *args)

        super(MatMult, self).__init__([A, B])

        if A.shape()[1] != B.shape()[0]:
            raise Exception("Cannot multiply %s by %s matrices." % (A.shape(), B.shape()))

        self.A, self.B = A, B

    def compute_value(self, rng, inputs):
        return np.dot( self.A.value(rng, inputs), self.B.value(rng, inputs) )

    def local_grad(self, parent, d_out_d_self):
        # TODO Allow for case A == B
        if parent == self.A:
            # Numpy is really, really bad.  Have to handle length-1 vectors differently.
            if len(self.B.shape()) == 1:
                return np.outer(d_out_d_self, self.B.value())
            else:
                return np.dot(d_out_d_self, self.B.value().T)
        elif parent == self.B:
            # Oh Numpy, you suck so much.
            if len(self.A.shape()) == 1:
                return np.outer(self.A.value(), d_out_d_self)
            else:
                return np.dot(self.A.value().T, d_out_d_self)
        else:
            raise Exception("Not a parent of me")

    def shape(self, inputs=None):
        if len(self.B.shape(inputs)) == 1:
            return (self.A.shape(inputs)[0],)
        else:
            return (self.A.shape(inputs)[0], self.B.shape(inputs)[1],)

class MatSum(Differentiable):
     
    def __init__(self, A, axis=None):
        super(MatSum, self).__init__([A])

        if axis is not None and type(axis) != int:
            raise Exception("Can only sum over one axis at a time.")

        self.A    = A
        self.axis = axis

    def compute_value(self, rng, inputs):
        if self.axis is None:
            # Handle the sum over all elements.
            A_val = self.A.value(rng, inputs)
            return np.sum(A_val).reshape([1] * len(A_val.shape))
        else:
            # Handle a sum and reexpansion over one dimension.
            return np.expand_dims(np.sum(self.A.value(rng, inputs), axis=self.axis), axis=self.axis)

    def local_grad(self, parent, d_out_d_self):
        assert parent is self.A
        return d_out_d_self * np.ones(self.A.shape())

    def shape(self, inputs=None):
        if self.axis is None:
            return tuple( [1] * len(self.A.shape(inputs)) )
        else:
            A_shape = list(self.A.shape(inputs))
            A_shape[self.axis] = 1
            return tuple(A_shape)

    def depends(self, other):
        return self.A == other or self.A.depends(other)

class MatAdd(Differentiable):

    def __init__(self, A, B, *args):
        # Recurse to handle lists of arguments.
        if len(args) > 0:
            B = MatAdd(B, *args)

        super(MatAdd, self).__init__([A,B])

        if broadcast(A.shape(), B.shape()) is None:
            raise Exception("Matrices are not broadcastable: %s vs %s" % (A.shape(), B.shape()))

        self.A = A
        self.B = B

    def compute_value(self, rng, inputs):
        return self.A.value(rng, inputs) + self.B.value(rng, inputs)

    def axes_for_sum(self, mat_shape, d_out_d_self_shape):
        mat_shape = list(mat_shape)
        d_out_d_self_shape = list(d_out_d_self_shape)
        to_sum = []
        for dim, sz in enumerate(d_out_d_self_shape[::-1]):
            if len(mat_shape) == 0:
                to_sum.append(len(d_out_d_self_shape)-dim-1)
            elif mat_shape.pop() == 1:
                to_sum.append(len(d_out_d_self_shape)-dim-1)
        return tuple(to_sum[::-1])

    def local_grad(self, parent, d_out_d_self):
        assert self.A is not self.B
        if np.atleast_1d(d_out_d_self).shape == parent.shape():
            return d_out_d_self
        else:
            broadcast_axes = self.axes_for_sum(parent.shape(), d_out_d_self.shape)
            return np.sum(d_out_d_self, axis=broadcast_axes).reshape(parent.shape())

    def shape(self, inputs=None):
        return broadcast(self.A.shape(inputs), self.B.shape(inputs))

class MatDet(Differentiable):
    pass

class MatLogDet(Differentiable):
    pass

class MatTrace(Differentiable):
    pass

class Transpose(Differentiable):

    def __init__(self, A, axes=None):
        super(Transpose, self).__init__([A])

        self.A    = A
        self.axes = axes

    def compute_value(self, rng, inputs):
        return np.transpose(self.A.value(rng, inputs), axes=self.axes)

    def local_grad(self, parent, d_out_d_self):
        if self.axes is None:
            return np.transpose(d_out_d_self)
        else:
            return np.transpose(d_out_d_self, axes=np.argsort(self.axes))

    def shape(self, inputs=None):
        if self.axes is None:
            return self.A.shape(inputs)[::-1]
        else:
            shape = self.A.shape(inputs)
            return tuple([shape[ii] for ii in self.axes])

class Reshape(Differentiable):

    def __init__(self, A, new_shape):
        super(Reshape, self).__init__([A])

        self.A         = A
        self.new_shape = new_shape

    def compute_value(self, rng, inputs):
        return np.reshape(self.A.value(rng, inputs), self.new_shape)

    def local_grad(self, parent, d_out_d_self):
        return np.reshape(d_out_d_self, self.A.shape())

    def shape(self, inputs=None):
        return self.new_shape

class Concatenate(Differentiable):

    def __init__(self, axis, A, B, *args):
        # Recurse to handle lists of arguments.
        if len(args) > 0:
            B = Concatenate(axis, B, *args)

        super(Concatenate, self).__init__([A, B])

        self.A = A
        self.B = B
        self.axis = axis

    def compute_value(self, rng, inputs):
        return np.concatenate((self.A.value(rng, inputs),
                               self.B.value(rng, inputs)), axis=self.axis)

    def local_grad(self, parent, d_out_d_self):
        assert self.A is not self.B
        local_grad_A, local_grad_B = np.split(d_out_d_self, [self.A.shape()[self.axis]], axis=self.axis)
        if parent is self.A:
            return local_grad_A
        elif parent is self.B:
            return local_grad_B
        else:
            raise Exception("Parent must be A or B")

    def shape(self, inputs=None):
        a_shape = list(self.A.shape(inputs))
        b_shape = list(self.B.shape(inputs))
        shape = a_shape
        shape[self.axis] = a_shape[self.axis] + b_shape[self.axis]
        return tuple(shape)

class TensorMult(Differentiable):
    pass
       
