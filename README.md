# fylr-sequence-plugin

This plugin allows the automatic filling of configurable empty fields in inserted objects based on sequential numbers.

## Base Configuration

<!-- todo -->

## FylrSequence class

This class handles multiple sequences using specialized objects. This means, in the datamodel there must be an additional objecttype which stores the latest used unique sequential number. Each objects represents a sequence

The objecttype has the following requirements:

* text field for the reference:
    * this field stores a (unique) identifier so the reference can by identified
    * it should have a `NOT NULL` constraint, so no sequence object without a reference can exist
    * it should have a `UNIQUE` constraint, so each sequence can be identified (the plugin will use the first object that fits)
* integer field:
    * this field stores the latest used sequential number
    * it should have a `NOT NULL` constraint, so no sequence object without a number can exist

The plugin will not check these requirements, but they are recommended. It iterates over the objects and updates the first object where the reference matches. If the number is not set, the plugin will always start with `1`.

The plugin uses the combination of the reference and the number to get the latest number to use as an offset, and the object ID and version if an object with the plugin reference exists.

The plugin determines how many numbers of the sequence it will use, and update the sequence object (or create a new one if the sequence is used for the first time). If another plugin instance has updated the sequence already, the versions will not match, and the plugin tries to repeat the process again. The actual objects are only updated after the sequence update was successful.

### Constructor

```!python
seq = sequence.FylrSequence(
    api_url,
    ref,
    access_token,
    sequence_objecttype,
    sequence_ref_field,
    sequence_num_field
)
```

All **parameters** are of the type `str`:

- `api_url`: complete server (fylr) url including the `/api/v1` path
- `ref`: unique name (reference) of the sequence
- `access_token`: OAuth2 access token for the fylr api
- `sequence_objecttype`: objecttype that stores the sequence(s)
- `sequence_ref_field`: name of the field that stores the reference
- `sequence_num_field`: name of the field that stores the number

### Getting the next free sequence number

```'!python
number = seq.get_next_number()
```

If an object with the reference `ref` exists, this method returns the next free sequence number. If no object exists yet, this method returns `1`.

### Updating the sequence number

This method should be called before any fylr objects are actually updated. If this method returns no error, it means that the sequence object was successfully updated. The new number should be calculated by adding the number of needed sequence values to the current value. The

```'!python
update_ok, error = seq.update(number)
```

**Parameter**:

- `number`: integer value with the new value for the sequence

**Return values**:

- `update_ok`: bool value that indicates if the sequence was updated successfully
- `error`: error message that something went really wrong, or `None`

The combination of the two return values is an indicator how the plugin should proceed:

- if `update_ok` is `true`, there is no problem and the plugin can use the sequential number(s)
    - `error` will be `None` and can be ignored
- if `update_ok` is `false`, check the `error`:
    - if the `error` is `None`, this is an indicator that the update was not possible because another plugin instance updated the same sequence in the meantime
        - in this case, the plugin should repeat the process and call the method `get_next_number()` again
    - if the error is not `None`, this indicates that the sequence can not be updated because of invalid data

**Errors**:

- if the number for the update is invalid (less or equal the current number), the error will be an object with the following content:
    ```!python
    {
        'current_numer': <?>,
        'new_number': <?>
    }
    ```
    - in this case, the plugin should calculate a new valid sequence number and repeat the update process

- if there were any server errors during the update, the error will include the statuscode and the content of the response:
    ```!python
    {
        'url': '<?>',
        'statuscode': <?>,
        'reponse': ''
    }
    ```
    - in this case, the plugin should not try to repeat the update request, but return an error to the fylr itself
