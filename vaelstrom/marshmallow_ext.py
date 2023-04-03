from marshmallow import fields, Schema
from pathlib import Path
from json import JSONEncoder

"""
support for pathlib.Path in marshmallow & marshmallow-dataclass
also support set in json encoder
"""


class PathField(fields.String):
    def _deserialize(self, *args, **kwargs):
        return Path(super()._deserialize(*args, **kwargs))

    def _serialize(self, *args, **kwargs):
        return super()._serialize(*args, **kwargs)


class BaseSchema(Schema):
    TYPE_MAPPING = {Path: PathField}


class SetEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return JSONEncoder.default(self, obj)
