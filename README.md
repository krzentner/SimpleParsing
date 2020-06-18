[![Build Status](https://travis-ci.org/lebrice/SimpleParsing.svg?branch=master)](https://travis-ci.org/lebrice/SimpleParsing)

# Simple, Elegant, Typed Argument Parsing <!-- omit in toc -->

`simple-parsing` allows you to transform your ugly `argparse` scripts into beautifully structured, strongly typed little works of art.
Using [dataclasses](https://docs.python.org/3.7/library/dataclasses.html), `simple-parsing` makes it easier to share and reuse command-line arguments - ***no more copy pasting!***

Supports inheritance, **nesting**, easy serialization to json/yaml, automatic help strings from comments, and much more!

```python
# examples/demo.py
from dataclasses import dataclass
from simple_parsing import ArgumentParser

parser = ArgumentParser()
parser.add_argument("--foo", type=int, default=123, help="foo help")

@dataclass
class Options:
    """ Help string for this group of command-line arguments """
    log_dir: str                # Help string for a required str argument    
    learning_rate: float = 1e-4 # Help string for a float argument

parser.add_arguments(Options, dest="options")

args = parser.parse_args("--log_dir logs --foo 123".split())
print(args.foo)     # 123
print(args.options) # Options(log_dir='logs', learning_rate=0.0001)
```

Additionally, `simple-parsing` makes it easier to document your arguments by generating `"--help"` strings directly from your source code!

```console
$ python examples/demo.py --help
usage: demo.py [-h] [--foo int] --log_dir str [--learning_rate float]

optional arguments:
  -h, --help            show this help message and exit
  --foo int             foo help (default: 123)

Options ['options']:
   Help string for this group of command-line arguments 

  --log_dir str         Help string for a required str argument (default:
                        None)
  --learning_rate float
                        Help string for a float argument (default: 0.0001)
```

## installation

`pip install simple-parsing`

## [Examples](examples/README.md)

## [API Documentation](docs/README.md) (Under construction)

## Features 
- ### [Automatic "--help" strings](examples/docstrings/README.md)

    As developers, we want to make it easy for people coming into our projects to understand how to run them. However, a user-friendly `--help` message is often hard to write and to maintain, especially as the number of arguments increases.

    With `simple-parsing`, your arguments and their decriptions are defined in the same place, making your code easier to read, write, and maintain.

- ### Modular, Reusable, Cleanly Grouped Arguments
    
    *(no more copy-pasting)*
        
    When you need to add a new group of command-line arguments similar to an existing one, instead of copy-pasting a block of `argparse` code and renaming variables, you can reuse your argument class, and let the `ArgumentParser` take care of adding `relevant` prefixes to the arguments for you:

    ```python
    parser.add_arguments(Options, dest="train")
    parser.add_arguments(Options, dest="valid")
    args = parser.parse_args()
    train_options: Options = args.train
    valid_options: Options = args.valid
    print(train_options)
    print(valid_options)
    ```
    ```console
    $ python examples/demo.py \
        --train.experiment_name "training" \
        --valid.experiment_name "validation"
    Options(experiment_name='training', learning_rate=0.0001)
    Options(experiment_name='validation', learning_rate=0.0001)
    ```
        
    These prefixes can also be set explicitly, or not be used at all. For more info, take a look at the [Prefixing Guide](examples/prefixing/README.md)

- [**Easy serialization**](examples/serialization/README.md): Easily save/load configs to `json` or `yaml`!. 
- [**Inheritance**!](examples/inheritance/README.md)
You can easily customize an existing argument class by extending it and adding your own attributes, which helps promote code reuse accross projects. For more info, take a look at the [inheritance example](examples/inheritance_example.py)

- [**Nesting**!](examples/nesting/README.md): Dataclasses can be nested within dataclasses, as deep as you need!
- [Easier parsing of lists and tuples](examples/container_types/README.md) : This is sometimes tricky to do with regular `argparse`, but `simple-parsing` makes it a lot easier by using the python's builtin type annotations to automatically convert the values to the right type for you.

    As an added feature, by using these type annotations, `simple-parsing` allows you to parse nested lists or tuples, as can be seen in [this example](examples/merging/README.md)

- [Enums support](examples/enums/README.md)

- (More to come!)


## Examples:
Additional examples for all the features mentioned above can be found in the [examples folder](examples/README.md)
