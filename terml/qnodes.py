import itertools
from collections import namedtuple
from terml.nodes import Term, Tag, coerceToTerm

class QTerm(namedtuple("QTerm", "functor data args span")):
    def _substitute(self, map):
        candidate = self.functor._substitute(map)[0]
        args = tuple(itertools.chain.from_iterable(a._substitute(map) for a in self.args))
        term = Term(candidate.tag, candidate.data, args, self.span)
        return [term]

    def substitute(self, map):
        return self._substitute(map)[0]

    def match(self, specimen, substitutionArgs=()):
        bindings = {}
        if self._match(substitutionArgs, [specimen], bindings, (), 1) == 1:
            return bindings
        raise TypeError("%r doesn't match %r" % (self, specimen))

    def _reserve(self):
        return 1

    def _match(self, args, specimens, bindings, index, max):
        if not specimens:
            return -1
        spec = self._coerce(specimens[0])
        if spec is None:
            return -1
        matches = self.functor._match(args, [spec.withoutArgs()], bindings, index, 1)
        if not matches:
            return -1
        if matches > 1:
            raise TypeError("Functor may only match 0 or 1 specimen")
        num = matchArgs(self.args, spec.args, args, bindings, index, len(spec.args))
        if len(spec.args) == num:
            if max >= 1:
                return 1
        return -1

    def _coerce(self, spec):
        if isinstance(spec, Term):
            newf = coerceToQuasiMatch(spec.withoutArgs(),
                                      self.functor.isFunctorHole,
                                      self.functor.functor)
            if newf is None:
                return None
            return Term(newf.asFunctor(), None, spec.args, None)
        else:
            return coerceToQuasiMatch(spec, self.functor.isFunctorHole,
                                      self.functor.functor)

    def __eq__(self, other):
        return (     self.functor, self.data, self.args
               ) == (other.functor, other.data, other.args)

    def asFunctor(self):
        if self.args:
            raise ValueError("Terms with args can't be used as functors")
        else:
            return self.functor

class QFunctor(namedtuple("QFunctor", "tag data span")):
    isFunctorHole = False
    def _reserve(self):
        return 1

    @property
    def name(self):
        return self.tag.name

    def _unparse(self, indentLevel=0):
        return self.tag._unparse(indentLevel)

    def _substitute(self, map):
        return [Term(self.tag, self.data, None, self.span)]

    def _match(self, args, specimens, bindings, index, max):
        if not specimens:
            return -1
        spec = coerceToQuasiMatch(specimens[0], False, self.tag)
        if spec is None:
            return -1
        if self.data is not None and self.data != spec.data:
            return -1
        if max >= 1:
            return 1
        return -1

    def asFunctor(self):
        return self

def matchArgs(quasiArglist, specimenArglist, args, bindings, index, max):
    specs = specimenArglist
    reserves = [q._reserve() for q in quasiArglist]
    numConsumed = 0
    for i, qarg in enumerate(quasiArglist):
        num = qarg._match(args, specs, bindings, index, max - sum(reserves[i + 1:]))
        if num == -1:
            return -1
        specs = specs[num:]
        max -= num
        numConsumed += num
    return numConsumed


def coerceToQuasiMatch(val, isFunctorHole, tag):
    from terml.twine import TwineText, TwineBytes
    if isFunctorHole:
        if val is None:
            result = Term(Tag("null"), None, None, None)
        elif isinstance(val, Term):
            if len(val.args) != 0:
                return None
            else:
                result = val
        elif isinstance(val, (TwineText, TwineBytes)):
            result = Term(Tag(val), val, None, val.span)
        elif isinstance(val, basestring):
            result = Term(Tag(val), None, None, None)
        elif isinstance(val, bool):
            result = Term(Tag(["false", "true"][val]), None, None, None)
        else:
            return None
    else:
        result = coerceToTerm(val)
    if tag is not None and result.tag != tag:
        return None
    return result

class _Hole(namedtuple("_Hole", "functor name isFunctorHole")):
    def _reserve(self):
        return 1

    def __repr__(self):
        return "term('%s')" % (self._unparse(4).replace("'", "\\'"))

    def match(self, specimen, substitutionArgs=()):
        bindings = {}
        if self._match(substitutionArgs, [specimen], bindings, (), 1) != -1:
            return bindings
        raise TypeError("%r doesn't match %r" % (self, specimen))


def _multiget(args, holenum, index, repeat):
    result = args[holenum]
    for i in index:
        if not isinstance(result, list):
            return result
        result = result[i]
    return result

def _multiput(bindings, holenum, index, newval):
    bits = bindings
    dest = holenum
    for it in index:
        next = bits[dest]
        if next is None:
            next = {}
            bits[dest] = next
        bits = next
        dest = it
    result = None
    if dest in bits:
        result = bits[dest]
    bits[dest] = newval
    return result

class ValueHole(_Hole):
    def _unparse(self, indentLevel=0):
        return "${%s}" % (self.name,)

    def _substitute(self, map):
        termoid = map[self.name]
        val = coerceToQuasiMatch(termoid, self.isFunctorHole, self.functor)
        if val is None:
            raise TypeError("%r doesn't match %r" % (termoid, self))
        return [val]

    def asFunctor(self):
        if self.isFunctorHole:
            return self
        else:
            return ValueHole(self.functor, self.name, True)


class PatternHole(_Hole):

    def _unparse(self, indentLevel=0):
        if self.functor:
            return "%s@{%s}" % (self.functor.name, self.name)
        else:
            return "@{%s}" % (self.name,)

    def _match(self, args, specimens, bindings, index, max):
        if not specimens:
            return -1
        spec = coerceToQuasiMatch(specimens[0], self.isFunctorHole, self.functor)
        if spec is None:
            return -1
        oldval = _multiput(bindings, self.name, index, spec)
        if oldval is None or oldval != spec:
            if max >= 1:
                return 1
        return -1


    def asFunctor(self):
        if self.isFunctorHole:
            return self
        else:
            return PatternHole(self.functor, self.name, True)

class QSome(namedtuple("_QSome", "value quant")):
    def _reserve(self):
        if self.quant == "+":
            return 1
        else:
            return 0
