# Step 11: Pydantic

> **What it covers:** BaseModel, Field(), validators, nested models, serialization, and structured output — turning LLM responses into validated, typed data.

---

## Foundational Concepts (read this first)

### What problem does Pydantic solve?

When you call an LLM, you get raw text back. If you ask it to extract "name, age, email", the response might be formatted as JSON, or as plain text, or as a list. You'd have to manually parse it, handle missing fields, deal with wrong types, and crash if the format changes.

Pydantic solves this by letting you **define a schema** (a class with typed fields), and then it handles validation, type coercion, and parsing automatically. If the data doesn't match the schema, Pydantic raises a clear error telling you exactly what went wrong.

### Coercion vs. strictness — what "validation" actually means

Pydantic's "validation" is not just checking — it's **parsing and conversion**. When you pass `"123"` (a string) to an `int` field, Pydantic converts it to `123`. This is called **coercion** (or lax mode), and it's the default. It's designed so that data from JSON (which only has strings for values) can flow into typed models without manual conversion.

You can opt into **strict mode**, where Pydantic rejects type mismatches instead of coercing them. We'll cover that below.

### The Rust core

pydantic-core — the engine that actually runs validation — is written in **Rust**, making Pydantic one of the fastest Python validation libraries. The Python layer (`pydantic`) is just the public API on top.

### What you'll use it for in AI Engineering

1. **Parsing LLM output** — get structured data back instead of raw text to parse manually.
2. **Defining tool schemas** — Pydantic models can be converted directly into the JSON schema format that Anthropic/OpenAI accept as tool definitions.
3. **Validating API input** — FastAPI uses Pydantic models as request/response schemas.
4. **Configuration management** — define config classes with typed fields and defaults.

---

## 11.1 — BaseModel & Field Types

### The simplest model

```python
from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str = "John Doe"

user = User(id="123")  # string "123" gets coerced to int 123
print(user.id)          # 123 (int)
print(user.name)        # John Doe (default used)
```

**What happens here:**
- `id: int` — required field, must be int (or coercible to int).
- `name: str = "John Doe"` — optional field with a default value.
- Pydantic checks types on instantiation. If validation fails, it raises `ValidationError`.
- Coercion happens automatically: `"123"` → `123`.

### Required vs. optional vs. nullable

```python
from pydantic import BaseModel

class User(BaseModel):
    a: int               # required
    b: int = 0           # optional (has default)
    c: int | None        # required, but can be None
    d: int | None = None # optional, defaults to None
```

`int | None` is the modern Python syntax. You can also use `Optional[int]` from `typing`.

### Common field types Pydantic handles

| Python type | What Pydantic accepts (lax mode) |
|---|---|
| `int` | int, float (truncated), string digits ("42") |
| `float` | float, int, string number ("3.14") |
| `str` | str, bytes, any object with `__str__` |
| `bool` | bool, int (0/1), string "true"/"false" |
| `datetime` | datetime object, ISO 8601 string, Unix timestamp |
| `list[int]` | list of ints, tuple of ints (coerced to list) |
| `dict[str, int]` | dict with string keys and int values |
| `UUID` | UUID object, string like "550e8400-..." |
| `EmailStr` | string that looks like an email (requires `email-validator`) |
| `UrlStr` | string that looks like a URL |
| `SecretStr` | string that's masked in repr (for passwords/keys) |

### Strict mode — no coercion

```python
from pydantic import BaseModel, Field

class User(BaseModel):
    id: int = Field(strict=True)  # rejects strings

User(id=123)       # OK
User(id="123")     # ValidationError: Input should be a valid integer
```

Per-field with `Field(strict=True)`, or for the whole model:

```python
from pydantic import BaseModel, ConfigDict

class User(BaseModel):
    model_config = ConfigDict(strict=True)
    id: int

User(id=123)       # OK
User(id="123")     # ValidationError
```

### TypeAdapter — validate a single type, not a model

Sometimes you just want to validate a standalone type:

```python
from pydantic import TypeAdapter

ta = TypeAdapter(list[int])
data = ta.validate_python([1, "2", 3])  # [1, 2, 3] — "2" coerced
```

Useful for validating individual values or simple structures without defining a model.

---

## 11.2 — Field() Constraints & Defaults

### Field() function

`Field()` adds metadata, constraints, and configuration to a field.

```python
from pydantic import BaseModel, Field

class Product(BaseModel):
    name: str = Field(max_length=50)           # string length cap
    price: float = Field(gt=0, le=9999.99)      # greater than, less or equal
    quantity: int = Field(ge=0, default=0)       # greater or equal
    description: str = Field(default="", min_length=10)
    code: str = Field(pattern=r"^[A-Z]{3}\d{4}$")  # regex pattern
```

### Available constraints

| Constraint | Applies to | Meaning |
|---|---|---|
| `gt` | numbers | greater than |
| `ge` | numbers | greater than or equal |
| `lt` | numbers | less than |
| `le` | numbers | less than or equal |
| `multiple_of` | numbers | must be a multiple of |
| `min_length` | strings, lists | minimum length |
| `max_length` | strings, lists | maximum length |
| `pattern` | strings | regex must match |
| `strict` | any | no coercion allowed |
| `frozen` | any | field can't be changed after creation |
| `alias` | any | alternative name for the field |
| `default` | any | default value |
| `default_factory` | any | callable that produces default |
| `validate_default` | any | validate the default value (normally skipped) |

### Default factory — for mutable defaults

A common Python pitfall: mutable defaults (like `[]` or `{}`) are shared across instances. Pydantic deep-copies them, but it's cleaner to use a factory:

```python
from pydantic import BaseModel, Field
from uuid import uuid4

class Order(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    tags: list[str] = Field(default_factory=list)
```

### The Annotated pattern — reusable metadata

Instead of `name: str = Field(max_length=50)`, you can attach metadata via `Annotated`:

```python
from typing import Annotated
from pydantic import BaseModel, Field

ShortString = Annotated[str, Field(max_length=50)]
PositiveInt = Annotated[int, Field(gt=0)]

class Product(BaseModel):
    name: ShortString
    price: PositiveInt
```

**Why this matters:** `ShortString` is a reusable type alias. Use it in 10 models, change the constraint once. Type checkers still see it as `str`/`int`.

### Aliases — mapping external field names

```python
from pydantic import BaseModel, Field

class User(BaseModel):
    full_name: str = Field(alias="fullName")

user = User(fullName="John Doe")  # alias on input
print(user.full_name)             # "John Doe" — Python name on access
print(user.model_dump(by_alias=True))  # {"fullName": "John Doe"}
```

Aliases let you accept camelCase JSON (from JavaScript APIs) while using snake_case in Python.

---

## 11.3 — Validators (field_validator vs. model_validator)

### When do you need custom validators?

Type hints cover simple constraints (range, length, pattern). Custom validators handle logic like:
- "password must match password_repeat"
- "start_date must be before end_date"
- "normalize this email to lowercase"
- "strip whitespace from this string"

### Field validators — run on individual fields

#### After validator (most common — run after type checks)

```python
from pydantic import BaseModel, field_validator

class User(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

user = User(email="  JOHN@Example.COM ")
print(user.email)  # john@example.com
```

The method receives the raw value and **must return the validated value**. The `@classmethod` is required.

#### After validator with ValidationInfo — access other fields

```python
from pydantic import BaseModel, field_validator, ValidationInfo

class User(BaseModel):
    password: str
    password_repeat: str

    @field_validator("password_repeat")
    @classmethod
    def passwords_match(cls, v: str, info: ValidationInfo) -> str:
        if v != info.data["password"]:
            raise ValueError("Passwords don't match")
        return v
```

**Caveat:** Fields are validated in definition order. You can only access fields defined *before* the current one.

#### Before validator — transform input before type checking

```python
from typing import Any
from pydantic import BaseModel, field_validator

class Model(BaseModel):
    numbers: list[int]

    @field_validator("numbers", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> Any:
        if not isinstance(v, list):
            return [v]
        return v

Model(numbers=5)     # numbers=[5] — single int wrapped in list
```

#### Plain validator — bypass all Pydantic type checking

```python
from typing import Any
from pydantic import BaseModel, field_validator

class Model(BaseModel):
    number: int

    @field_validator("number", mode="plain")
    @classmethod
    def custom_parse(cls, v: Any) -> Any:
        # You take full control — no Pydantic validation runs
        return int(v) * 2 if isinstance(v, str) else v * 2
```

Returns whatever you return. No further validation happens.

#### Wrap validator — run code before AND after Pydantic's validation

```python
from typing import Any
from pydantic import (
    BaseModel, Field, ValidationError,
    ValidatorFunctionWrapHandler, field_validator,
)

class Model(BaseModel):
    my_string: str = Field(max_length=5)

    @field_validator("my_string", mode="wrap")
    @classmethod
    def truncate(cls, v: Any, handler: ValidatorFunctionWrapHandler) -> str:
        try:
            return handler(v)              # try normal validation
        except ValidationError as e:
            if "too long" in str(e):
                return handler(v[:5])     # truncate and retry
            raise
```

### Model validators — run on the whole object

After all field validators pass, model validators run on the complete instance.

#### After model validator

```python
from typing_extensions import Self
from pydantic import BaseModel, model_validator

class Event(BaseModel):
    start: int
    end: int

    @model_validator(mode="after")
    def check_order(self) -> Self:
        if self.start >= self.end:
            raise ValueError("start must be before end")
        return self  # must return self
```

#### Before model validator — raw dict before any field validation

```python
from typing import Any
from pydantic import BaseModel, model_validator

class Model(BaseModel):
    name: str

    @model_validator(mode="before")
    @classmethod
    def strip_extra(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data.pop("internal_id", None)  # remove before field validation
        return data
```

### Which mode to use when

| Mode | When |
|---|---|
| `field_validator` (after) | Validate/transform a single field's value. |
| `field_validator` (before) | Pre-process raw input before type checking. |
| `field_validator` (plain) | Completely replace validation logic. |
| `field_validator` (wrap) | Surround normal validation with try/except. |
| `model_validator` (after) | Cross-field validation (start < end, passwords match). |
| `model_validator` (before) | Pre-process the entire input dict. |

---

## 11.4 — Nested Models

### Models containing other models

```python
from pydantic import BaseModel

class Address(BaseModel):
    city: str
    country: str

class User(BaseModel):
    name: str
    address: Address  # another model

user = User(name="John", address={"city": "Berlin", "country": "DE"})
print(user.address.city)    # Berlin
print(user.address.country) # DE
```

Pass a dict, and Pydantic auto-converts it into the nested model. This is extremely useful when parsing nested JSON from an LLM response.

### Lists of models

```python
class Product(BaseModel):
    name: str
    price: float

class Order(BaseModel):
    items: list[Product]

order = Order(items=[{"name": "Apple", "price": 0.50}, {"name": "Banana", "price": 0.30}])
print(order.items[0].name)  # Apple
```

### Self-referencing / recursive models

```python
from __future__ import annotations
from pydantic import BaseModel

class TreeNode(BaseModel):
    value: int
    children: list[TreeNode] | None = None

tree = TreeNode(value=1, children=[TreeNode(value=2)])
```

The `from __future__ import annotations` makes all annotations strings (deferred evaluation), which lets you reference `TreeNode` inside its own definition.

---

## 11.5 — Serialization (model_dump / model_dump_json)

Once validated, you need to send the data somewhere — to a database, an API response, or back to the LLM as context.

### model_dump() — to a Python dict

```python
from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str = "John"

user = User(id=1)
print(user.model_dump())         # {"id": 1, "name": "John"}
print(user.model_dump(exclude={"name"}))  # {"id": 1}
print(user.model_dump(include={"id"}))    # {"id": 1}
```

### model_dump_json() — to a JSON string

```python
data = user.model_dump_json()
print(data)         # '{"id": 1, "name": "John"}'
print(type(data))   # <class 'str'>
```

Useful for API responses and file storage.

### Key serialization parameters

| Parameter | Effect |
|---|---|
| `exclude` | Exclude specific fields |
| `include` | Include only specific fields |
| `by_alias` | Use alias names instead of Python names |
| `exclude_unset` | Only include fields explicitly set |
| `exclude_defaults` | Remove fields equal to their defaults |
| `exclude_none` | Remove None fields |
| `mode="json"` | Force JSON-compatible types (e.g., tuples → lists) |
| `indent` | Pretty-print JSON (only for `model_dump_json`) |

### Round-trip safety

```python
# dict → model → dict gives you clean, validated data
raw = {"id": "42", "name": "Alice"}
user = User.model_validate(raw)
clean = user.model_dump()
# clean = {"id": 42, "name": "Alice"}  — id is now int, not string
```

### Serialization aliases

Control how field names appear in output:

```python
from pydantic import BaseModel, Field

class User(BaseModel):
    name: str = Field(serialization_alias="userName")

user = User(name="John")
print(user.model_dump(by_alias=True))  # {"userName": "John"}
```

### Polymorphic serialization

If a field's type is `User` but you pass a subclass `Admin(User)`:

```python
from pydantic import BaseModel, SerializeAsAny

class User(BaseModel):
    name: str

class Admin(User):
    role: str = "admin"

class Container(BaseModel):
    as_any: SerializeAsAny[User]  # serialize ALL fields of subclass
    as_user: User                 # only serialize User fields

c = Container(as_any=Admin(name="Alice"), as_user=Admin(name="Bob"))
print(c.model_dump())
# {"as_any": {"name": "Alice", "role": "admin"}, "as_user": {"name": "Bob"}}
```

Without `SerializeAsAny`, Pydantic only includes fields from the declared type. With it, it respects the actual runtime type.

---

## 11.6 — Structured Output / Tool Schemas

### Why this matters for AI Engineering

When you call an LLM, you can give it a JSON schema and say "return data matching this schema." The modern Anthropic/OpenAI tool-calling format accepts JSON Schema — which Pydantic can auto-generate from any model.

### Generating a JSON schema from a model

```python
from pydantic import BaseModel, Field

class ExtractPerson(BaseModel):
    name: str = Field(description="The person's full name")
    age: int = Field(description="Their age in years")
    email: str | None = Field(default=None, description="Email if mentioned")

print(ExtractPerson.model_json_schema())
```

Output:

```json
{
  "properties": {
    "name": {"title": "Name", "type": "string"},
    "age": {"title": "Age", "type": "integer"},
    "email": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": null}
  },
  "required": ["name", "age"],
  "title": "ExtractPerson",
  "type": "object"
}
```

This is **exactly** the format Anthropic's `tools` parameter expects. If you need OpenAI's format:

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "extract_person",
            "description": "Extract person details from text",
            "parameters": ExtractPerson.model_json_schema(),
        },
    }
]
```

### Using with Anthropic tools

```python
import anthropic
from pydantic import BaseModel, Field

class WeatherQuery(BaseModel):
    location: str = Field(description="City and state, e.g. San Francisco, CA")
    unit: str = Field(default="celsius", pattern="^(celsius|fahrenheit)$")

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    tools=[
        {
            "name": "get_weather",
            "description": "Get current weather",
            "input_schema": WeatherQuery.model_json_schema(),
        }
    ],
    messages=[{"role": "user", "content": "What's the weather in Berlin?"}],
)
```

### Parsing an LLM's structured output back into a model

When the LLM returns a text response that happens to be JSON, or when you get `tool_use.input` back:

```python
# From tool_use.input (already a dict)
raw_llm_output = {"location": "Berlin", "unit": "celsius"}
query = WeatherQuery.model_validate(raw_llm_output)
print(query.location)  # Berlin

# From a JSON string
raw_json = '{"location": "Berlin", "unit": "celsius"}'
query = WeatherQuery.model_validate_json(raw_json)
```

### Nested structured output

```python
from pydantic import BaseModel, Field

class Item(BaseModel):
    name: str
    price: float

class Receipt(BaseModel):
    store: str
    items: list[Item]
    total: float

receipt = Receipt.model_validate_json('''
{
    "store": "SuperMart",
    "items": [{"name": "Milk", "price": 2.50}, {"name": "Bread", "price": 1.20}],
    "total": 3.70
}
''')
```

### Validation guard with try/except

```python
from pydantic import BaseModel, ValidationError

class ExtractPerson(BaseModel):
    name: str
    age: int

raw = {"name": 42, "age": "old"}  # both wrong types
try:
    person = ExtractPerson.model_validate(raw)
except ValidationError as e:
    print(e)
    # Shows exactly which fields failed and why
```

---

## Additional Concepts Worth Knowing

### ConfigDict — model-level configuration

```python
from pydantic import BaseModel, ConfigDict

class StrictModel(BaseModel):
    model_config = ConfigDict(
        strict=True,       # no coercion for all fields
        frozen=True,       # model is immutable after creation
        extra="forbid",     # reject unknown fields (default: "ignore")
        populate_by_name=True,  # allow field name OR alias on input
    )
    name: str
    age: int
```

Common config settings:

| Setting | Values | Effect |
|---|---|---|
| `strict` | `True`/`False` | Global strict mode |
| `frozen` | `True`/`False` | Immutable instance |
| `extra` | `"ignore"`/`"forbid"`/`"allow"` | How to handle extra fields |
| `populate_by_name` | `True`/`False` | Accept field names alongside aliases |
| `validate_default` | `True`/`False` | Validate default values |
| `from_attributes` | `True`/`False` | Allow validating from ORM objects |

### RootModel — wrap a single type

```python
from pydantic import RootModel

# Instead of: class Wrapper(BaseModel): items: list[str]
# You can use RootModel for cleaner serialization

class Items(RootModel[list[str]]):
    pass

items = Items(["a", "b", "c"])
print(items.model_dump())       # ["a", "b", "c"]
print(items.model_dump_json())  # '["a","b","c"]'
```

Useful when your entire model is just one type (a list, a string, a dict).

### Private attributes — non-field data on models

```python
from pydantic import BaseModel, PrivateAttr

class User(BaseModel):
    name: str
    _cache: dict = PrivateAttr(default_factory=dict)

user = User(name="John")
user._cache["key"] = "value"  # accessible, not part of schema
print(user.model_dump())      # {"name": "John"} — _cache excluded
```

---

## Quick Reference

| Task | Method |
|---|---|
| Create a model | `class Foo(BaseModel):` with typed fields |
| Validate a dict | `Foo.model_validate(data)` |
| Validate JSON string | `Foo.model_validate_json(json_str)` |
| Validate a single type | `TypeAdapter(list[int]).validate_python(...)` |
| Convert to dict | `foo.model_dump()` |
| Convert to JSON | `foo.model_dump_json()` |
| Add field constraints | `Field(gt=0, le=100, max_length=50, pattern=r"...")` |
| Custom field logic | `@field_validator("field_name")` |
| Cross-field logic | `@model_validator(mode="after")` |
| Generate JSON Schema | `Foo.model_json_schema()` |
| Create without validation | `Foo.model_construct(...)` |
| Copy (with optional updates) | `foo.model_copy(update={"key": val})` |

---

## What to Practice

1. Define a `BaseModel` with at least 5 fields of different types (int, str, float, datetime, list).
2. Add `Field()` constraints to each field (min/max, length, pattern).
3. Create a nested model (model A contains model B).
4. Write a `@field_validator` that transforms a value (e.g., strip/uppercase a string).
5. Write a `@model_validator` that checks a cross-field rule (e.g., end > start).
6. Use `model_validate_json()` to parse an LLM's JSON response into your model.
7. Generate a JSON schema with `model_json_schema()` and use it as a tool definition.
8. Try strict mode: pass "42" to an `int` field with `strict=True` and catch the error.
