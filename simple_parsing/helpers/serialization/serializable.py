"""
"""

import copy
import inspect
import json
import logging
import warnings
from dataclasses import Field, asdict, dataclass, fields, is_dataclass
from functools import singledispatch
from pathlib import Path
from typing import *
from typing import IO, TypeVar
from collections import OrderedDict
import typing_inspect as tpi

from .decoding import decoding_fns, register_decoding_fn
from .encoding import SimpleJsonEncoder, encode

logger = logging.getLogger(__file__)

Dataclass = TypeVar("Dataclass")
D = TypeVar("D", bound="Serializable")

try:
    import yaml
    def ordered_dict_constructor(loader: yaml.Loader, node: yaml.Node):
        value = loader.construct_sequence(node)
        return OrderedDict(value)

    def ordered_dict_representer(dumper: yaml.Dumper, instance: OrderedDict) -> yaml.Node:
        node = dumper.represent_sequence("OrderedDict", instance.items())
        return node

    yaml.add_representer(OrderedDict, ordered_dict_representer)
    yaml.add_constructor("OrderedDict", ordered_dict_constructor)

except ImportError:
    pass


@dataclass
class Serializable:
    """Makes a dataclass serializable to and from dictionaries.

    Supports JSON and YAML files for now.

    >>> from dataclasses import dataclass
    >>> from simple_parsing.helpers import Serializable
    >>> @dataclass
    ... class Config(Serializable):
    ...   a: int = 123
    ...   b: str = "456"
    ... 
    >>> config = Config()
    >>> config
    Config(a=123, b='456')
    >>> config.to_dict()
    {"a": 123, "b": 456}
    >>> config_ = Config.from_dict({"a": 123, "b": 456})
    Config(a=123, b='456')
    >>> assert config == config_
    """
    subclasses: ClassVar[List[Type["Serializable"]]] = []
    decode_into_subclasses: ClassVar[bool] = False

    def __init_subclass__(cls, decode_into_subclasses: bool=None, add_variants: bool=True):
        logger.debug(f"Registering a new Serializable subclass: {cls}")
        super().__init_subclass__()
        if decode_into_subclasses is None:
            # if decode_into_subclasses is None, we will use the value of the
            # parent class, if it is also a subclass of JsonSerializable.
            # Skip the class itself as well as object.
            parents = cls.mro()[1:-1] 
            logger.debug(f"parents: {parents}")

            for parent in parents:
                if parent in Serializable.subclasses and parent is not Serializable:
                    assert issubclass(parent, Serializable)
                    decode_into_subclasses = parent.decode_into_subclasses
                    logger.debug(f"Parent class {parent} has decode_into_subclasses = {decode_into_subclasses}")
                    break

        cls.decode_into_subclasses = decode_into_subclasses or False
        if cls not in Serializable.subclasses:
            Serializable.subclasses.append(cls)

        register_decoding_fn(cls, cls.from_dict, add_variants=add_variants)

    def to_dict(self, dict_factory:Type[Dict]=dict) -> Dict:
        """ Serializes this dataclass to a dict.
        
        NOTE: This 'extends' the `asdict()` function from
        dataclasses, allowing us to not include some fields in the dict, or
        to perform some kind of custom encoding (for instance, detaching tensors
        before serializing the dataclass to a dict)
        """
        d: Dict[str, Any] = dict_factory()
        for f in fields(self):
            name = f.name
            value = getattr(self, name)
            T = f.type
            # TODO: Do not include in dict if some corresponding flag was set in metadata!
            include_in_dict = f.metadata.get("to_dict", True)
            if not include_in_dict:
                continue

            d[name] = encode(value)
        return d

    @classmethod
    def from_dict(cls: Type[D], obj: Dict, drop_extra_fields: bool=None) -> D:
        """ Parses an instance of `cls` from the given dict.
        
        NOTE: If the `decode_into_subclasses` class attribute is set to True (or
        if `decode_into_subclasses=True` was passed in the class definition),
        then if there are keys in the dict that aren't fields of the dataclass,
        this will decode the dict into an instance the first subclass of `cls`
        which has all required field names present in the dictionary.
        
        Passing `drop_extra_fields=None` (default) will use the class attribute
        described above.
        Passing `drop_extra_fields=True` will decode the dict into an instance
        of `cls` and drop the extra keys in the dict.
        Passing `drop_extra_fields=False` forces the above-mentioned behaviour.
        """
        drop_extra_fields = drop_extra_fields or not cls.decode_into_subclasses
        return from_dict(cls, obj, drop_extra_fields=drop_extra_fields)

    def dump(self, fp: IO[str], dump_fn=json.dump, **kwargs) -> None:
        dump_fn(self.to_dict(), fp, **kwargs)

    def dumps(self, dump_fn=json.dumps, **kwargs) -> str:
        return dump_fn(self.to_dict(), **kwargs)

    @classmethod
    def load(cls: Type[D], path: Union[Path, str, IO[str]], drop_extra_fields: bool=None, load_fn=None, **kwargs) -> D:
        if isinstance(path, str):
            path = Path(path)

        if load_fn is None and isinstance(path, Path):
            if path.suffix == ".yml":
                return cls.load_yaml(path, drop_extra_fields=drop_extra_fields, **kwargs)
            elif path.suffix == ".json":
                return cls.load_json(path, drop_extra_fields=drop_extra_fields, **kwargs)
            elif path.suffix == ".pth":
                import torch
                load_fn = torch.loads
            elif path.suffix == ".npy":
                import numpy as np
                load_fn = np.load
            warnings.warn(RuntimeWarning(
                f"Not sure how to deserialize contents of {path} to a dict, as no "
                f" load_fn was passed explicitly. Will try to use {load_fn} as the "
                f"load function, based on the path name."    
            )) 

        if load_fn is None:
            raise RuntimeError(
                f"Unable to determine what function to use in order to load "
                f"path {path} into a dictionary, since no load_fn was passed, "
                f"and the path doesn't have an unfamiliar extension.."
            )

        if isinstance(path, Path):
            path = path.open()
        return cls._load(path, load_fn=load_fn, drop_extra_fields=drop_extra_fields, **kwargs)

    @classmethod
    def _load(cls: Type[D], fp: IO[str], drop_extra_fields: bool=None, load_fn=json.load, **kwargs) -> D:
        d = load_fn(fp, **kwargs)
        return cls.from_dict(d, drop_extra_fields=drop_extra_fields)

    def save(self, path: Union[str, Path], dump_fn=None, **kwargs) -> None:
        if isinstance(path, str):
            path = Path(path)

        if dump_fn is None and isinstance(path, Path):
            if path.suffix == ".yml":
                return self.save_yaml(path, **kwargs)
            elif path.suffix == ".json":
                return self.save_json(path, **kwargs)
            elif path.suffix == ".pth":
                import torch
                dump_fn = torch.save
            elif path.suffix == ".npy":
                import numpy as np
                dump_fn = np.save
            warnings.warn(RuntimeWarning(
                f"Not 100% sure how to deserialize contents of {path} to a "
                f"file as no dump_fn was passed explicitly. Will try to use "
                f"{dump_fn} as the serialization function, based on the path "
                f"suffix." 
            ))

        if dump_fn is None:
            raise RuntimeError(
                f"Unable to determine what function to use in order to load "
                f"path {path} into a dictionary, since no load_fn was passed, "
                f"and the path doesn't have an unfamiliar extension.."
            )
        self._save(path, dump_fn=dump_fn, **kwargs)

    def _save(self, path: Union[str, Path], dump_fn=json.dump, **kwargs) -> None:    
        with open(path, "w") as fp:
            dump_fn(self.to_dict(), fp, **kwargs)

    @classmethod
    def loads(cls: Type[D], s: str, drop_extra_fields: bool=None, load_fn=json.loads, **kwargs) -> D:
        d = load_fn(s, **kwargs)
        return cls.from_dict(d, drop_extra_fields=drop_extra_fields)

    def save_yaml(self, path: Union[str, Path], **kwargs) -> None:
        import yaml
        kwargs.setdefault("Loader", yaml.FullLoader)
        self.save(path, dump_fn=yaml.dump)

    @classmethod
    def load_yaml(cls: Type[D], path: Union[str, Path], **kwargs) -> D:
        import yaml
        kwargs.setdefault("Loader", yaml.FullLoader)
        with open(path) as fp:
            return cls._load(fp, load_fn=yaml.load, **kwargs)

    def save_json(self, path: Union[str, Path], **kwargs) -> None:
        kwargs.setdefault("cls", SimpleJsonEncoder)
        self._save(path, dump_fn=lambda p, v: json.dump(p, v, **kwargs))

    @classmethod
    def load_json(cls: Type[D], path: Union[str, Path], **kwargs) -> D:
        # kwargs.setdefault("cls", SimpleJsonEncoder)
        with open(path) as fp:
            return cls._load(fp, load_fn=json.load, **kwargs)

    # def dump(self, fp: IO[str], **dump_kwargs) -> None:
    #     dump_kwargs.setdefault("cls", SimpleJsonEncoder)
    #     json.dump(self.to_dict(), fp, **dump_kwargs)

    # def dumps(self, **dumps_kwargs) -> str:
    #     dumps_kwargs.setdefault("cls", SimpleJsonEncoder)
    #     return json.dumps(self, **dumps_kwargs)
    
    # @classmethod
    # def load(cls: Type[D], fp: IO[str], drop_extra_fields: bool=None, **load_kwargs) -> D:
    #     return cls.from_dict(json.load(fp, **load_kwargs), drop_extra_fields=drop_extra_fields)
    
    # @classmethod
    # def loads(cls: Type[D], s: str, drop_extra_fields: bool=None, **loads_kwargs) -> D:
    #     return cls.from_dict(json.loads(s, **loads_kwargs), drop_extra_fields=drop_extra_fields)


def is_list_type(t: Type) -> bool:
    if tpi.is_generic_type(t):
        origin = tpi.get_origin(t)
        logger.debug(f"type {t} is a generic with origin {origin}")
        t = origin
    assert inspect.isclass(t), t
    return issubclass(t, (list, List))


def is_dict_type(t: Type) -> bool:
    if tpi.is_generic_type(t):
        origin = tpi.get_origin(t)
        logger.debug(f"type {t} is a generic with origin {origin}")
        t = origin
    return issubclass(t, (dict, Dict, Mapping))


def get_dataclass_type_from_forward_ref(forward_ref: Type, Serializable=Serializable) -> Optional[Type]:
    arg = tpi.get_forward_arg(forward_ref)
    potential_classes: List[Type] = []

    for serializable_class in Serializable.subclasses:
        if serializable_class.__name__ == arg:
            potential_classes.append(serializable_class)

    if not potential_classes:
        logger.warning(
            f"Unable to find a corresponding type for forward ref "
            f"{forward_ref} inside the registered {Serializable} subclasses. "
            f"(Consider adding {Serializable} as a base class to <{arg}>? )."
        )
        return None
    elif len(potential_classes) > 1:
        logger.warning(
            f"More than one potential {Serializable} subclass was found for "
            f"forward ref '{forward_ref}'. The appropriate dataclass will be "
            f"selected based on the matching fields. \n"
            f"Potential classes: {potential_classes}"
        )
        return Serializable
    else:
        assert len(potential_classes) == 1
        return potential_classes[0]


def get_actual_type(field_type: Type) -> Type:
    if tpi.is_union_type(field_type):
        logger.debug(f"field has union type: {field_type}")
        t = get_first_non_None_type(field_type)
        logger.debug(f"First non-none type: {t}")
        if t is not None:
            field_type = t

    if tpi.is_forward_ref(field_type):
        logger.debug(f"field_type {field_type} is a forward ref.")
        dc = get_dataclass_type_from_forward_ref(field_type)
        logger.debug(f"Found the corresponding type: {dc}")
        if dc is not None:
            field_type = dc
    return field_type


def decode_field(field: Field, field_value: Any, drop_extra_fields: bool=None) -> Any:
    name = field.name
    field_type = field.type
    logger.info(f"name = {name}, field_type = {field_type} drop_extra_fields is {drop_extra_fields}")

    if field_type in {str, int, bool, float}:
        return field_type(field_value)

    if field_type in decoding_fns:
        logger.info(f"We have a decoding function for the type {field_type}")
        decoding_function = decoding_fns[field_type]
        return decoding_function(field_value)
    
    field_type = get_actual_type(field_type)
    logger.info(f"Actual type: {field_type}")

    if is_dataclass(field_type):
        return from_dict(field_type, field_value, drop_extra_fields)
    
    elif is_list_type(field_type):
        item_type = get_list_item_type(field_type)
        logger.debug(f"{field_type} is a List[{item_type}]")

        if item_type and is_dataclass(item_type):    
            new_field_list_value: List = []
            for item_args in field_value:
                # Parse an instance from the dict.
                if isinstance(item_args, dict):
                    item_instance = from_dict(item_type, item_args, drop_extra_fields)
                    new_field_list_value.append(item_instance)
                else:
                    new_field_list_value.append(item_args)
            return new_field_list_value

    elif is_dict_type(field_type):
        key_type, value_type = get_key_and_value_types(field_type)
        logger.info(f"{field_type} is a Dict[{key_type}, {value_type}]")
        if value_type:
            new_field_dict_value: Dict = {}
            for k, item_args in field_value.items():
                # Parse an instance from the dict.
                if isinstance(item_args, dict):
                    item_instance = from_dict(value_type, item_args, drop_extra_fields)
                    new_field_dict_value[k] = item_instance
                else:
                    new_field_dict_value[k] = item_args
            return new_field_dict_value
    
    return field_value


def from_dict(cls: Type[Dataclass], d: Dict[str, Any], drop_extra_fields: bool=None) -> Dataclass:
    if d is None:
        return None
    obj_dict: Dict[str, Any] = d.copy()

    init_args: Dict[str, Any] = {}
    non_init_args: Dict[str, Any] = {}
        
    if drop_extra_fields is None:
        decode_into_subclasses = getattr(cls, "decode_into_subclasses", False)
        drop_extra_fields = not decode_into_subclasses
        logger.debug(f"drop_extra_fields is None, using the value of {drop_extra_fields} from the attribute on class {cls}")
        if cls is Serializable:
            logger.debug(f"The class that was passed is DictSerializable, which means that we should set drop_extra_fields to False.")
            drop_extra_fields = False

    logger.info(f"from_dict called with cls {cls}, drop extra fields: {drop_extra_fields}")

    for field in fields(cls):
        name = field.name
        field_type = field.type
               
        if name not in obj_dict:
            logger.warning(f"Couldn't find the field '{name}' in the dict with keys {d.keys()}")
            continue

        field_value = obj_dict.pop(name)
        field_value = decode_field(field, field_value)

        if field.init:
            init_args[name] = field_value
        else:
            non_init_args[name] = field_value
    
    extra_args = obj_dict
    
    if extra_args:
        if drop_extra_fields:
            logger.warning(f"Dropping extra args {extra_args}")
            extra_args.clear()
        
        elif issubclass(cls, Serializable):
            # Use the first Serializable derived class that has all the required fields.
            logger.debug(f"Missing field names: {extra_args.keys()}")  

            # Find all the "registered" subclasses of `cls`. (from Serializable)
            derived_classes: List[Type] = []
            for subclass in Serializable.subclasses:
                if issubclass(subclass, cls) and subclass is not cls:
                    derived_classes.append(subclass)
            logger.debug(f"All serializable derived classes of {cls} available: {derived_classes}")

            from itertools import chain
            # All the arguments that the dataclass should be able to accept in its 'init'.
            req_init_field_names = set(chain(extra_args, init_args))
            
            # Sort the derived classes by their number of init fields, so we choose the first one that fits.
            derived_classes.sort(key=lambda dc: len(get_init_fields(dc)))

            for child_class in derived_classes:
                logger.debug(f"class name: {child_class.__name__}, mro: {child_class.mro()}") 
                child_init_fields: Dict[str, Field] = get_init_fields(child_class)
                child_init_field_names = set(child_init_fields.keys())
                
                if child_init_field_names >= req_init_field_names:
                    logger.debug(f"Using child class {child_class} instead of {cls}, since it has all the required fields.")
                    return from_dict(child_class, d, drop_extra_fields=False)
        else:
            raise RuntimeError(f"Unexpected arguments for class {cls}: {extra_args}")
    
    init_args.update(extra_args)
    try:
        instance = cls(**init_args)  # type: ignore
    except TypeError as e:
        # raise RuntimeError(f"Couldn't instantiate class {cls} using init args {init_args}.")
        raise RuntimeError(f"Couldn't instantiate class {cls} using init args {init_args.keys()}: {e}")

    for name, value in non_init_args.items():
        logger.debug(f"Setting non-init field '{name}' on the instance.")
        setattr(instance, name, value)
    return instance


def get_key_and_value_types(dict_type: Type[Dict], Serializable=Serializable) -> Tuple[Optional[Type], Optional[Type]]:
    args = tpi.get_args(dict_type)
    if len(args) != 2:
        logger.debug(f"Weird.. the type {dict_type} doesn't have 2 args: {args}")
        return None, None
    K_ = args[0]
    V_ = args[1]
    # Get rid of Unions or ForwardRefs or Optionals
    V_ = get_actual_type(V_)

    logger.debug(f"K_: {K_}, V_: {V_}")
    if isinstance(V_, tuple):
        V_ = get_first_non_None_type(V_)
    elif tpi.is_optional_type(V_):
        logger.debug(f"V_ is optional: {V_}")
        V_ = get_first_non_None_type(V_)
    return K_, V_


def get_list_item_type(list_type: Type[List]) -> Optional[Type]:
    logger.debug(f"list type: {list_type}")
    args = tpi.get_args(list_type)
    logger.debug(f"args = {args}")
    
    if not args:
        return None

    assert isinstance(args, tuple), args
    if isinstance(args[0], tuple):
        args = args[0]
    assert isinstance(args, tuple), args
    logger.debug(f"args tuple: {args}")
    V_ = get_first_non_None_type(args)
    logger.debug(f"item type: {V_}")
    assert V_ is not None
    V_ = get_actual_type(V_)

    assert not isinstance(V_, tuple), V_
    return V_


def get_init_fields(dataclass: Type) -> Dict[str, Field]:
    result: Dict[str, Field] = {}
    for field in fields(dataclass):
        if field.init:
            result[field.name] = field
    return result


def get_first_non_None_type(optional_type: Union[Type, Tuple[Type, ...]]) -> Optional[Type]:
    if not isinstance(optional_type, tuple):
        optional_type = tpi.get_args(optional_type)
    for arg in optional_type:
        if arg is not Union and arg is not type(None):
            logger.debug(f"arg: {arg} is not union? {arg is not Union}")
            logger.debug(f"arg is not type(None)? {arg is not type(None)}")
            return arg
    return None


def is_dataclass_or_optional_dataclass_type(t: Type) -> bool:
    """ Returns wether `t` is a dataclass type or an Optional[<dataclass type>].
    """
    return is_dataclass(t) or (tpi.is_optional_type(t) and
        is_dataclass(tpi.get_args(t)[0])
    )
