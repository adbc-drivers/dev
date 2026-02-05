<!--
  Copyright (c) 2026 ADBC Drivers Contributors

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
-->

# Validation Suite

## Setup

1. Build your driver into the `build/` directory (required):

   ```shell
   # The validation suite expects:
   # build/libadbc_driver_{driver_id}.dylib (macOS)
   # build/libadbc_driver_{driver_id}.so (Linux)
   ```

2. Set the environment variable:

   ```shell
   export {driver_id_upper}_DSN="your-connection-string"
   ```

## Running Tests

Option 1: Using adbc-validation CLI:

```shell
adbc-validation run
```

Option 2: Using pixi:

```shell
cd validation
pixi run validate
```

Option 3: Using pytest directly:

```shell
cd validation
pytest -v
```

## Generating Documentation

Generate validation results:

```shell
adbc-validation docs
```

Documentation will be created in `validation/docs/`.
