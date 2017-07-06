#!/usr/bin/python3
# -*- coding: utf-8 -*-
""" An implementation of concatenable lists
"""


class catlist_node(object):
    def __init__(self, car, cdr=None):
        self.car = car
        self.cdr = cdr

class catlist(object):
    def __init__(self, iterable=None):
        self.first = None
        self.last = None
        self.n = 0
        self.dead = False
        if iterable:
            for x in iterable:
                self.append(x)

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        assert(i in [0, -1, self.n-1])
        if i == 0:
            return self.first.car
        return self.last.car

    def append(self, x):
        assert(not self.dead)
        node = catlist_node(x)
        if self.n == 0:
            self.first = node
            self.last = node
        else:
            self.last.cdr = node
            self.last = node
        self.n += 1

    def extend(self, other):
        assert(not self.dead)
        assert(not other.dead)
        assert type(other) is catlist
        if other.n == 0: return
        if self.n == 0:
            self.first = other.first
            self.last = other.last
        else:
            self.last.cdr = other.first
            self.last = other.last
        self.n += other.n
        other.dead = True

    def __iter__(self):
        assert(not self.dead)
        it = self.first
        while not it is None:
            yield it.car
            it = it.cdr

    def __str__(self):
        assert(not self.dead)
        return "〈{}〉)".format(",".join([repr(x) for x in self]))

    def __repr__(self):
        assert(not self.dead)
        return "catlist([{}]))".format(",".join([repr(x) for x in self]))

if __name__ == "__main__":
    a = range(10)
    c = catlist()
    for x in a:
        c.append(x)
    print(c)
    c2 = catlist(range(11,20))
    print(c2)
    c.extend(c2)
    print(c)
    print(c2)
    c3 = catlist([str(x) for x in c])
    print(",".join(c3))
