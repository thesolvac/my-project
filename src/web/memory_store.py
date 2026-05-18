from __future__ import annotations

import copy
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

class _FakeObjectId:
    _counter = 0

    def __init__(self, value: str | None = None):
        if value:
            self._v = str(value).zfill(24)[:24]
        else:
            _FakeObjectId._counter += 1
            self._v = f"{_FakeObjectId._counter:024x}"

    def __str__(self):  return self._v
    def __repr__(self): return f"ObjectId('{self._v}')"
    def __eq__(self, other): return str(self) == str(other)
    def __hash__(self): return hash(self._v)

ObjectId = _FakeObjectId

class _InsertResult:
    def __init__(self, oid): self.inserted_id = oid

class _UpdateResult:
    def __init__(self): self.modified_count = 1

class _MemCollection:

    def __init__(self):
        self._docs: list[dict] = []

    def insert_one(self, doc: dict) -> _InsertResult:
        d = copy.deepcopy(doc)
        if "_id" not in d:
            d["_id"] = _FakeObjectId()
        self._docs.append(d)
        return _InsertResult(d["_id"])

    def update_one(self, filt: dict, update: dict, upsert: bool = False):
        for doc in self._docs:
            if self._match(doc, filt):
                ops = update.get("$set", {})
                for k, v in ops.items():
                    doc[k] = v
                inc = update.get("$inc", {})
                for k, v in inc.items():
                    doc[k] = doc.get(k, 0) + v
                return _UpdateResult()
        if upsert:
            new_doc = {k: v for k, v in filt.items()}
            for k, v in update.get("$set", {}).items():
                new_doc[k] = v
            self.insert_one(new_doc)
        return _UpdateResult()

    def find_one(self, filt: dict = None, projection: dict = None):
        for doc in self._docs:
            if self._match(doc, filt or {}):
                return copy.deepcopy(doc)
        return None

    def find(self, filt: dict = None, projection: dict = None):
        return _Cursor(
            [copy.deepcopy(d) for d in self._docs if self._match(d, filt or {})]
        )

    def count_documents(self, filt: dict = None) -> int:
        return sum(1 for d in self._docs if self._match(d, filt or {}))

    def create_index(self, *args, **kwargs):
        pass

    def aggregate(self, pipeline: list) -> list:
        docs = [copy.deepcopy(d) for d in self._docs]
        for stage in pipeline:
            if "$group" in stage:
                docs = self._group(docs, stage["$group"])
            elif "$sort" in stage:
                for field, direction in reversed(list(stage["$sort"].items())):
                    docs.sort(key=lambda d: d.get(field, 0) or 0,
                              reverse=(direction == -1))
            elif "$limit" in stage:
                docs = docs[: stage["$limit"]]
        return docs

    @staticmethod
    def _match(doc: dict, filt: dict) -> bool:
        for key, val in filt.items():
            if key == "$or":
                if not any(_MemCollection._match(doc, sub) for sub in val):
                    return False
            elif key == "$and":
                if not all(_MemCollection._match(doc, sub) for sub in val):
                    return False
            elif isinstance(val, dict):
                dv = doc.get(key)
                for op, ov in val.items():
                    if op == "$gt"  and not (dv is not None and dv >  ov): return False
                    if op == "$gte" and not (dv is not None and dv >= ov): return False
                    if op == "$lt"  and not (dv is not None and dv <  ov): return False
                    if op == "$lte" and not (dv is not None and dv <= ov): return False
                    if op == "$ne"  and dv == ov: return False
                    if op == "$in"  and dv not in ov: return False
            else:
                if str(doc.get(key, "")) != str(val) and doc.get(key) != val:
                    return False
        return True

    @staticmethod
    def _group(docs: list, spec: dict) -> list:
        groups: dict[Any, dict] = {}
        id_field = spec.get("_id")

        for doc in docs:
            if isinstance(id_field, str) and id_field.startswith("$"):
                key = doc.get(id_field[1:])
            else:
                key = id_field

            if key not in groups:
                groups[key] = {"_id": key}

            for out_field, expr in spec.items():
                if out_field == "_id":
                    continue
                if isinstance(expr, dict):
                    op   = list(expr.keys())[0]
                    src  = list(expr.values())[0]
                    fval = doc.get(src[1:]) if isinstance(src, str) and src.startswith("$") else src

                    if op == "$sum":
                        groups[key][out_field] = groups[key].get(out_field, 0) + (fval or 0)
                    elif op == "$avg":
                        prev = groups[key].get(f"__sum_{out_field}", 0)
                        cnt  = groups[key].get(f"__cnt_{out_field}", 0)
                        groups[key][f"__sum_{out_field}"] = prev + (fval or 0)
                        groups[key][f"__cnt_{out_field}"] = cnt + 1
                        n = groups[key][f"__cnt_{out_field}"]
                        groups[key][out_field] = groups[key][f"__sum_{out_field}"] / n if n else 0
                    elif op == "$max":
                        cur = groups[key].get(out_field)
                        groups[key][out_field] = fval if cur is None else max(cur, fval or cur)
                    elif op == "$min":
                        cur = groups[key].get(out_field)
                        groups[key][out_field] = fval if cur is None else min(cur, fval or cur)

        return list(groups.values())

class _Cursor:

    def __init__(self, docs: list):
        self._docs = docs

    def sort(self, key_or_list, direction=None):
        if isinstance(key_or_list, list):
            for field, d in reversed(key_or_list):
                self._docs.sort(key=lambda doc: doc.get(field, 0) or 0,
                                reverse=(d == -1))
        else:
            self._docs.sort(key=lambda doc: doc.get(key_or_list, 0) or 0,
                            reverse=(direction == -1))
        return self

    def limit(self, n: int):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)

class MemoryDatabase:

    def __init__(self):
        self._collections: dict[str, _MemCollection] = defaultdict(_MemCollection)

    def __getattr__(self, name: str) -> _MemCollection:
        return self._collections[name]

    def __getitem__(self, name: str) -> _MemCollection:
        return self._collections[name]

    def create_collection(self, name: str, **_):
        return self._collections[name]

_memory_db = MemoryDatabase()

def get_memory_db() -> MemoryDatabase:
    return _memory_db
