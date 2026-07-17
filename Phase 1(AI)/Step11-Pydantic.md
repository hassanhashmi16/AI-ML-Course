# Step 11: Pydantic

> **What it covers:** BaseModel, Field(), validators, nested models, serialization, and structured output — turning LLM responses into validated, typed data.

---

## Foundational Concepts

### What is a schema?

A **schema** is a blueprint that describes what data should look like — what fields exist, what types they should be, which ones are required, what constraints they have. Think of it like a form with labeled fields: "name must be text, age must be a number between 0 and 150, email is optional."

Pydantic lets you define schemas as Python classes. You write the schema once, and Pydantic handles checking incoming data against it.

### What problem does Pydantic solve?

When you call an LLM, you get raw text back. If you ask it to extract "name, age, email", the response might be JSON, or plain text, or a list. Without Pydantic, you'd write fragile parsing code that crashes the moment the format shifts slightly.

Pydantic gives you a **contract**: define the expected shape, and if the data doesn't match, you get a clear error showing exactly what's wrong and where.

### Validation vs. parsing vs. coercion

These three words are often used interchangeably in Pydantic docs, but they mean different things:

- **Validation** — checking if data is correct. "Is this a valid email?"
- **Parsing** — reading raw data and interpreting it. "Turn this JSON string into Python objects."
- **Coercion** — automatically converting data to the right type instead of rejecting it. "`"42"` becomes `42`."

Pydantic does all three at once. When you do `User(id="42")`, it parses the input, coerces `"42"` to `42`, then validates that `42` satisfies any constraints (like `ge=0`).

### What is serialization?

**Serialization** is converting a Python object into a format you can send somewhere — a JSON string for an API response, a dict for storing in a database, or back to the LLM as context. The opposite direction (raw data → Python object) is **deserialization**.

Pydantic handles both directions:
- Deserialization: `User.model_validate(raw_dict)` — raw data → validated model
- Serialization: `user.model_dump()` — model → clean dict

This is called a **round-trip**: dict → model (validated) → dict (cleaned).

### Why Pydantic is so widely used

- **Rust core** — The actual validation engine (`pydantic-core`) is written in Rust. It's one of the fastest Python validation libraries.
- **JSON Schema generation** — Every Pydantic model can produce a JSON Schema, which is exactly what LLM tool-calling APIs consume.
- **Ecosystem** — FastAPI, LangChain, Hugging Face, SQLModel, and thousands of other packages use it. Learning Pydantic unlocks all of them.
- **Type hint integration** — Your IDE understands Pydantic models. Autocomplete, type checking, and refactoring all work naturally.

### How you'll use it in AI Engineering

1. **Parsing LLM output** — Get structured data back instead of raw text to parse manually.
2. **Defining tool schemas** — Pydantic models convert directly to the JSON Schema format that Anthropic/OpenAI accept as tool definitions.
3. **Validating API input** — FastAPI uses Pydantic models as request/response schemas.
4. **Configuration management** — Define config classes with typed fields and defaults instead of raw dictionaries.

---

## 11.1 — BaseModel & Field Types

### The simplest model

```python
from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str = "John Doe"
```

That's it. You just defined a schema. Now let's use it:

```python
user = User(id="123")  # string "123" gets coerced to int 123
print(user.id)          # 123 (int, not string)
print(user.name)        # "John Doe" (default was used)
```

**Step by step, this is what happens when you call `User(id="123")`:**

1. Pydantic receives `{"id": "123"}`.
2. It checks the `id` field — annotated as `int`, but got a string.
3. In lax mode, it tries to coerce. `"123"` can be parsed as an integer → becomes `123`.
4. `name` has a default, so it uses `"John Doe"` without validation.
5. Everything passes → returns a `User` instance.

If coercion fails, Pydantic raises `ValidationError`.

### Required vs. optional vs. nullable

```python
from pydantic import BaseModel

class User(BaseModel):
    a: int               # required — must provide this
    b: int = 0           # optional — has a default, can skip it
    c: int | None        # required — but None is an accepted value
    d: int | None = None # optional — and defaults to None
```

**Why `c` is required but `d` is not:**

The **type annotation** (`int | None`) defines what values are *accepted*. The **default value** (`= None`) defines whether the field is *optional*.

- `c` has no default → you must pass it. But you can pass `None`.
- `d` has `= None` as default → you can skip it. It'll be `None`.

This trips people up because `Optional[int]` *sounds* like "optional," but in Pydantic/Python typing, it only means "this can also be None."

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
| `EmailStr` | string that looks like an email |
| `SecretStr` | string masked in repr (for passwords/API keys) |

### Strict mode — no coercion, exact types only

By default, Pydantic tries to be helpful — it coerces types. But sometimes you want to reject anything that isn't exactly right:

```python
from pydantic import BaseModel, Field

class User(BaseModel):
    id: int = Field(strict=True)

User(id=123)       # ✅ OK
User(id="123")     # ❌ ValidationError: Input should be a valid integer
```

Or strict for the whole model at once:

```python
from pydantic import BaseModel, ConfigDict

class User(BaseModel):
    model_config = ConfigDict(strict=True)
    id: int
```

### TypeAdapter — validating a single value without a model

Sometimes you don't need a full model. You just want to validate one value:

```python
from pydantic import TypeAdapter

ta = TypeAdapter(list[int])
result = ta.validate_python([1, "2", 3])
print(result)  # [1, 2, 3] — "2" coerced to 2
```

---

## 11.2 — Field() Constraints & Defaults

### What is Field()?

`Field()` is a function that attaches extra information to a model field — constraints (must be > 0), metadata (aliases, descriptions), and behavior (strict, frozen).

```python
from pydantic import BaseModel, Field

class Product(BaseModel):
    name: str = Field(max_length=50)         # max string length
    price: float = Field(gt=0, le=9999.99)    # greater than 0, ≤ 9999.99
    quantity: int = Field(ge=0, default=0)     # ≥ 0
    code: str = Field(pattern=r"^[A-Z]{3}$")  # must match regex
    description: str = Field(default="", min_length=10)
```

### Full constraint reference

| Constraint | Applies to | Meaning |
|---|---|---|
| `gt` | numbers | Greater than this value |
| `ge` | numbers | Greater than or equal to this value |
| `lt` | numbers | Less than this value |
| `le` | numbers | Less than or equal to this value |
| `multiple_of` | numbers | Must be a multiple of this value |
| `min_length` | strings, lists | Minimum number of characters/items |
| `max_length` | strings, lists | Maximum number of characters/items |
| `pattern` | strings | Must match this regular expression |
| `strict` | any | No coercion — exact type required |
| `frozen` | any | Field cannot be changed after creation |
| `alias` | any | Alternative name for the field (useful for JSON mapping) |
| `default` | any | Default value if none provided |
| `default_factory` | any | Callable that generates the default value |
| `validate_default` | any | Also validate the default value |

### Default factory — solving the mutable default problem

A classic Python pitfall:

```python
def bad(items=[]):  # same list shared across all calls!
    items.append(1)
    return items
```

Pydantic protects you from this with default factories:

```python
from pydantic import BaseModel, Field

class Order(BaseModel):
    tags: list[str] = Field(default_factory=list)
    # Each instance gets its own fresh list
```

You can also use a lambda for more complex defaults:

```python
from uuid import uuid4

class Order(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
```

### The Annotated pattern — reusable type aliases

Instead of repeating `Field(max_length=50)` everywhere, you can create a reusable type alias:

```python
from typing import Annotated
from pydantic import BaseModel, Field

ShortString = Annotated[str, Field(max_length=50)]

class Product(BaseModel):
    name: ShortString    # same as writing Field(max_length=50)
    sku: ShortString

class Customer(BaseModel):
    name: ShortString    # reuse the same constraint
```

**Why this matters:** Change `ShortString` in one place and every model using it updates. Your IDE still sees these as `str`, so autocomplete and type checking work normally.

### Aliases — mapping external field names to Python names

Real-world APIs often use camelCase (`firstName`). Python convention is snake_case (`first_name`). Aliases bridge the gap:

```python
from pydantic import BaseModel, Field

class User(BaseModel):
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")

user = User(firstName="John", lastName="Doe")  # alias on input
print(user.first_name)   # "John" — Python name internally
print(user.model_dump(by_alias=True))  # {"firstName": "John", "lastName": "Doe"}
```

---

## 11.3 — Validators

### When do you need custom validators?

Type hints handle simple constraints — ranges, lengths, patterns. But real-world logic is more complex:

- "Password must match password_repeat"
- "Start date must be before end date"
- "Strip whitespace and normalize this email to lowercase"

For these, you write a **validator** — a method that runs during validation and can transform or reject values.

### The two categories of validators

There are two, and the distinction is critical:

| Validator | Runs on | Can see | Use for |
|---|---|---|---|
| `field_validator` | A single field | Only that field's value (+ earlier fields) | Transform or reject one value |
| `model_validator` | The whole model | All fields at once | Cross-field rules |

### Field validators — one field at a time

#### After validator (default — runs after Pydantic's type checks)

```python
from pydantic import BaseModel, field_validator

class User(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

user = User(email="  JOHN@Example.COM ")
print(user.email)  # "john@example.com"
```

The method receives the raw value and **must return the validated value**. The `@classmethod` decorator is required.

#### Validating against another field's value

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

**Caveat:** Fields are validated in definition order. You can only access fields defined *before* the current one. If `password_repeat` came before `password` in the class, this would fail.

#### Before validator — raw input before Pydantic touches it

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

Model(numbers=5)       # numbers=[5] — wrapped in list
Model(numbers=[1, 2])  # numbers=[1, 2] — unchanged
```

The input is raw — could be a dict, int, string, anything. You return what Pydantic should validate next.

### Model validators — the "everything look right?" check

Model validators run after every single field has been individually validated. They get the complete instance and can check relationships between fields.

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

This is the **right way** to do cross-field validation. Don't try to check `start` vs `end` inside a `field_validator` — you won't have both values.

#### Before model validator — preprocess the raw input dict

```python
from typing import Any
from pydantic import BaseModel, model_validator

class Model(BaseModel):
    name: str

    @model_validator(mode="before")
    @classmethod
    def clean_input(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data.pop("internal_id", None)  # remove before field validation
        return data
```

### Which validator to use when — the decision tree

```
Do you need to check or transform a single field?
  ├── Yes → field_validator
  │         └── Good for: trimming whitespace, normalizing format, range checks
  └── No → Do you need to check a relationship between fields?
            ├── Yes → model_validator(mode="after")
            │         └── Good for: start < end, passwords match
            └── No → Before model validator
                      └── Good for: stripping unwanted keys from raw input
```

---

## 11.4 — Nested Models

### Models containing other models

Real data is nested. A user has an address. An order has products. Pydantic handles this naturally:

```python
from pydantic import BaseModel

class Address(BaseModel):
    city: str
    country: str

class User(BaseModel):
    name: str
    address: Address  # another model as a field type

user = User(
    name="John",
    address={"city": "Berlin", "country": "DE"},  # dict auto-converted
)
print(user.address.city)  # "Berlin" — accessed as a model attribute
```

Pydantic automatically converts the dict into an `Address` instance. You don't need to manually create it.

### Lists of models

```python
class Product(BaseModel):
    name: str
    price: float

class Order(BaseModel):
    items: list[Product]

order = Order(items=[
    {"name": "Apple", "price": 0.50},
    {"name": "Banana", "price": 0.30},
])
print(order.items[0].name)   # "Apple"
```

Each dict in the list is validated against `Product`.

### Self-referencing models (trees, linked lists)

For recursive structures like file trees or org charts:

```python
from __future__ import annotations
from pydantic import BaseModel

class TreeNode(BaseModel):
    value: int
    children: list[TreeNode] | None = None

tree = TreeNode(value=1, children=[TreeNode(value=2)])
```

The `from __future__ import annotations` makes all annotations deferred strings, so Python doesn't try to look up `TreeNode` before the class is fully defined.

---

## 11.5 — Serialization

### What "serialization" means

Serialization is the process of converting a Python object into a format that can be stored, transmitted, or logged:
- **Python mode** → dict (via `model_dump()`)
- **JSON mode** → JSON string (via `model_dump_json()`)

The opposite direction — raw data back into a model — is **deserialization** (via `model_validate()` or `model_validate_json()`).

### model_dump() — to a Python dict

```python
from pydantic import BaseModel

class User(BaseModel):
    id: int
    name: str = "John"

user = User(id=1)
print(user.model_dump())          # {"id": 1, "name": "John"}
print(user.model_dump(exclude={"name"}))  # {"id": 1}
print(user.model_dump(include={"id"}))    # {"id": 1}
```

### model_dump_json() — to a JSON string

```python
data = user.model_dump_json()
print(data)          # '{"id": 1, "name": "John"}'
print(type(data))    # <class 'str'>

# With formatting:
data = user.model_dump_json(indent=2)
```

### Serialization parameters explained

| Parameter | What it does | Example |
|---|---|---|
| `include` | **Whitelist** — only include these fields | `include={"name"}` → `{"name": "John"}` |
| `exclude` | **Blacklist** — skip these fields | `exclude={"password"}` → everything else |
| `exclude_unset` | Skip fields that used their default | If `age=18` was the default, it's omitted |
| `exclude_defaults` | Skip fields equal to their default value | Even if explicitly set, skipped if value == default |
| `exclude_none` | Skip any field that is `None` | |
| `by_alias` | Use alias names as keys | `alias="userName"` → `"userName": "John"` |
| `mode="json"` | Convert to JSON-safe types but return a dict | tuples → lists, datetime → string |
| `indent` | Pretty-print JSON | Only for `model_dump_json()` |

### The round-trip concept

```python
# Raw data (from API, file, LLM)
raw = {"id": "42", "name": "Alice"}

# Validate and convert to model
user = User.model_validate(raw)

# Convert back to clean, validated dict
clean = user.model_dump()
# clean = {"id": 42, "name": "Alice"}
# Note: id is now int, not string
```

This is a **round-trip**: dirty data → validated model → clean data. The output is guaranteed to conform to your schema.

### Polymorphic serialization — handling subclasses

If you have a base type `User` and a subclass `Admin(User)` that adds a `role` field:

```python
from pydantic import BaseModel, SerializeAsAny

class User(BaseModel):
    name: str

class Admin(User):
    role: str = "admin"

class Container(BaseModel):
    user: SerializeAsAny[User]   # serialize including subclass fields
    normal: User                  # only serialize base class fields

c = Container(user=Admin(name="Alice"), normal=Admin(name="Bob"))
print(c.model_dump())
# {"user": {"name": "Alice", "role": "admin"}, "normal": {"name": "Bob"}}
```

Without `SerializeAsAny`, Pydantic only includes fields from the declared type. With it, it looks at the actual runtime type and includes everything.

---

## 11.6 — Structured Output / Tool Schemas

### Why this is the most important section for AI Engineering

When you call an LLM with a tool definition, you pass a **JSON Schema** describing what arguments the tool accepts. Pydantic can auto-generate this JSON Schema from any model. This means:

1. You define the schema **once** as a Pydantic model.
2. You use `model_json_schema()` to generate the tool definition.
3. The LLM returns structured data matching that schema.
4. You parse it back into the model with `model_validate()`.

No manual dict fiddling. The schema is the source of truth.

### Generating a JSON Schema

```python
from pydantic import BaseModel, Field

class ExtractPerson(BaseModel):
    name: str = Field(description="The person's full name")
    age: int = Field(description="Their age in years")
    email: str | None = Field(default=None, description="Email if mentioned")

schema = ExtractPerson.model_json_schema()
```

`schema` is a dict like this:

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

This is **exactly what Anthropic's `input_schema` expects**.

### Using with Anthropic tool calling

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
    tools=[{
        "name": "get_weather",
        "description": "Get current weather",
        "input_schema": WeatherQuery.model_json_schema(),
    }],
    messages=[{"role": "user", "content": "What's the weather in Berlin?"}],
)
```

### Parsing LLM responses back into models

```python
# When the LLM returns a tool_use block, .input is already a dict
raw_output = {"location": "Berlin", "unit": "celsius"}
query = WeatherQuery.model_validate(raw_output)
print(query.location)  # "Berlin"

# If the LLM returns JSON as text
raw_json = '{"location": "Berlin", "unit": "celsius"}'
query = WeatherQuery.model_validate_json(raw_json)
```

### Handling invalid LLM output gracefully

```python
from pydantic import BaseModel, ValidationError

class ExtractPerson(BaseModel):
    name: str
    age: int

llm_response = {"name": 42, "age": "old"}  # both wrong types
try:
    person = ExtractPerson.model_validate(llm_response)
except ValidationError as e:
    print(e.errors())
    # Shows: name had wrong type, age had wrong type
```

Never trust LLM output. Always wrap in try/except.

---

## Additional Concepts

### ConfigDict — model-level configuration

```python
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(
        strict=True,              # no coercion — exact types required
        frozen=True,              # instance is immutable after creation
        extra="forbid",           # reject unknown fields (default: "ignore")
        populate_by_name=True,    # accept both field name and alias on input
    )
    name: str
    age: int
```

Common config settings:

| Setting | Values | Effect |
|---|---|---|
| `strict` | `True`/`False` | Global strict mode for all fields |
| `frozen` | `True`/`False` | Immutable — can't change fields after creation |
| `extra` | `"ignore"`, `"forbid"`, `"allow"` | How to handle fields not in the schema |
| `populate_by_name` | `True`/`False` | Allow using Python field names even with aliases |
| `validate_default` | `True`/`False` | Validate default values (normally skipped) |
| `from_attributes` | `True`/`False` | Allow validating from arbitrary objects (ORM mode) |

### RootModel — when your whole model is just one type

```python
from pydantic import RootModel

class Items(RootModel[list[str]]):
    pass

items = Items(["a", "b", "c"])
print(items.model_dump())       # ["a", "b", "c"]  — cleaner than wrapping in a dict
print(items.model_dump_json())  # '["a","b","c"]'
```

Useful when the entire output is a single list or dict, not an object with named fields.

### PrivateAttr — runtime-only data, not part of the schema

```python
from pydantic import BaseModel, PrivateAttr

class User(BaseModel):
    name: str
    _cache: dict = PrivateAttr(default_factory=dict)  # underscore prefix required

user = User(name="John")
user._cache["key"] = "value"       # accessible at runtime
print(user.model_dump())           # {"name": "John"} — _cache excluded
```

Private attributes start with `_`, are never validated or serialized, and don't appear in schemas. Useful for caching, temporary state, and internal plumbing.

---

## Theory Summary

Here's the mental model for Pydantic — the concepts you should internalize, not just the method names.

**Data has shape.** Every piece of data you handle — an LLM response, an API payload, a config file — has an expected structure. Pydantic lets you declare that structure as code. This is called a **schema**.

**Validation is a pipeline.** When data enters a model, it flows through stages: raw input → coercion → type checking → field validators → model validators → clean instance. Each stage catches different kinds of problems. The earlier stages handle mechanical issues (wrong type, missing field). The later stages handle business logic (passwords match, dates make sense).

**Serialization is the reverse.** Going from a model back to raw data is not the same as going forward. Types get converted (int stays int, but a complex field might simplify). This is why `model_dump()` and `model_validate()` are separate operations — they aren't symmetrical.

**Coercion is a feature, not a bug.** Pydantic's lax mode deliberately converts types. `"42"` becomes `42`. `"2024-01-01"` becomes a datetime object. This is essential because JSON only has a handful of types (string, number, bool, null) while Python has many more (int, float, datetime, UUID, Decimal). Coercion bridges that gap. If you want exact types, use strict mode.

**A schema is also a contract.** When you pass a JSON Schema to an LLM as a tool definition, you're saying "only return data matching this shape." When you parse the result back through that same schema, you're enforcing the contract. If the LLM deviates, you catch it immediately instead of debugging a cryptic crash downstream.

**Nested schemas compose.** A model can contain other models. Lists of models. Dicts of models. Self-referential models (trees). The total complexity of your data is the sum of its parts, and Pydantic validates every level automatically.

**Validation context matters.** Field validators run in field definition order. Later fields can't depend on the validated value of earlier fields — at least not safely. For cross-field rules, use model validators. This ordering constraint is not a bug; it's a deliberate design that keeps validation predictable and parallelizable.

**The Rust core is invisible but real.** You never interact with `pydantic-core` directly. But it's why Pydantic can validate millions of records per second. The Python layer is just the API surface.

---

## Quick Reference

| What you want | How to do it |
|---|---|
| Define a schema | `class Foo(BaseModel):` with typed fields |
| Validate a dict | `Foo.model_validate(data)` |
| Validate JSON string | `Foo.model_validate_json(json_str)` |
| Validate a single value | `TypeAdapter(int).validate_python("42")` |
| Convert model to dict | `foo.model_dump()` |
| Convert model to JSON | `foo.model_dump_json()` |
| Generate LLM tool schema | `Foo.model_json_schema()` |
| Skip validation (trusted data) | `Foo.model_construct(data)` |
| Copy with changes | `foo.model_copy(update={"key": val})` |
| Add numeric constraint | `Field(gt=0, le=100)` |
| Add string constraint | `Field(min_length=1, max_length=50, pattern=r"...")` |
| Custom field logic | `@field_validator("field_name")` |
| Cross-field logic | `@model_validator(mode="after")` |

---

## What to Practice

1. Define a `BaseModel` with fields of different types (int, str, float, datetime, list, dict).
2. Add `Field()` constraints to each field — try gt, max_length, pattern.
3. Create a nested model (a User with an Address).
4. Write a `@field_validator` that strips/normalizes a string.
5. Write a `@model_validator` that checks a cross-field relationship.
6. Use `model_json_schema()` to generate a tool definition, then use it in an Anthropic API call.
7. Parse the LLM's response back into a model with `model_validate_json()`.
8. Try strict mode — pass `"42"` to an `int` field with `strict=True` and observe the error.
9. Experiment with serialization options: exclude, exclude_unset, by_alias.
