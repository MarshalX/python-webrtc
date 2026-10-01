# WebIDL comparison

Compares the public API of the `webrtc` package with the WebIDL of the specifications it implements, taken from
`wpt/interfaces/`. Updating the WPT checkout brings in spec changes, and new differences fail the tests.

It needs the WPT checkout and PythonMonkey (see [tests/wpt/README.md](../wpt/README.md)) and Python 3.10 or later;
otherwise the tests are skipped. The IDL is parsed by `webidl2.js` of the checkout, the parser of idlharness, in a
child process.

## Running

```sh
uv run pytest tests/idl                # compare every definition with expectations.json
uv run python -m tests.idl             # print every difference, + for new ones and - for gone ones
uv run python -m tests.idl update      # record the current differences as expected
```

## What is compared

`spec.FILES` lists the IDL files and which definitions to take from each. Every interface, dictionary and enum maps
to the object of the same name in `webrtc`:

- enums: the values.
- dictionaries: every member has a snake_case name and a camelCase alias, required members have no default, and
  annotations name the IDL types the member refers to.
- interfaces: attributes and methods by name and alias, read-only or writable attributes, static and async methods
  (a promise is a coroutine or returns a future), `on<event>` handlers against `_events`, maplike and iterable
  declarations against the Python protocols.
- arguments of methods and constructors: names, order, optional and variadic ones, and types. A dictionary argument
  is either one parameter or keyword parameters for its members, like `create_offer(*, ice_restart=False)`, whose
  members are then checked one by one. Overloads match the one the signature fits best.
- public members the IDL doesn't have.

## Expectations

`expectations.json` lists the differences per definition. A definition fails when its differences change in either
direction, so after aligning the API or updating WPT, run `update` and commit the new expectations with the change.
