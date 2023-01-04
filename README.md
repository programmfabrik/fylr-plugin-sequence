# fylr-plugin-sequence

This plugin allows the automatic filling of configurable empty fields in inserted objects based on sequential numbers.

The automatic filling of empty fields can be configured [in a general way](#base-configuration) per objecttype and field, or for pool managed objects, with more complex patterns based on [pool settings](#pool-settings).

To store the current value of different sequences, this plugin uses a specialized objecttype. This objecttype **must be added to the datamodel**, and must fullfil these following requirements:

* **text** field for the reference:
    * this field stores a **(unique) identifier** so the sequence can be identified by this **reference**
    * it should have a `NOT NULL` constraint, so no sequence object without a reference can exist
    * it should have a `UNIQUE` constraint, so each sequence can be identified (the plugin will use the first object that fits)
* **integer** field:
    * this field stores the latest used **sequential number**
    * it should have a `NOT NULL` constraint, so no sequence object without a number can exist

## Base Configuration

### Settings for the sequence objecttype

* **Objecttype**
    * select the objecttype that is used to store the sequences
* **Reference Field**
    * text field
    * this field stores a **(unique) identifier** so the sequence can be identified by this **reference**
* **Number Field**
    * integer field
    * this field stores the latest used **sequential number**

### Settings for the updated fields in objects

For each objecttype one or more fields can be defined which are checked by the plugin if they are empty. In this case, the plugin will use the template to format a string that contains the sequential number. The selected fields must be text fields.

* **Objecttype**
    * select the objecttype to be updated
* **Text Field**
    * select the text field to be updated
* **Template for field content**
    * insert the template for the text that will be generated
    * the template must comply to the specific format below
* **Start offset of the sequence**
    * optional integer value to add to the sequential number
* **Only fill this field if a new object is inserted**
    * if activated, this option causes updated objects (version > 1) to be skipped by the plugin
    * activate this option if you only want to fill fields once when the object is created

**Template format**

The template must contain a placeholder for the sequential number, as well as an optional prefix and suffix. The placeholder must be in the [`printf` format style of python3](https://docs.python.org/3/library/stdtypes.html#printf-style-string-formatting) and must be compatible to format an integer value.

Please keep in mind, that only a **single, unnamed placeholder** can be used, otherwise an internal formatting error will be caused.

Some examples for useful placeholders inside the template are:

| Template | Description | Example |
|---|---|---|
| `%d` | Simple number | `13` |
| `%04d` | Number with four trailing zeros | `0027` |
| `%08x` | Hexadecimal number with eight trailing zeros | `00000BB9` |


## Pool Settings

Empty fields in objects can be filled by using templates based on pool settings. When an object is inserted/updated, based on the pool of the object, the configured templates of the pool are applied.

A template is a text with a combination of fixed text and [template placeholders](#template-placeholders). The placeholders are replaced by values of the pool and the pools parent, as well as sequential numbers.

The pool settings are inherited from parent pools. This means, if there is a template configured for a specific pair of objecttype and field, all children of the pool also get this template. If a child pool has a template for objecttype and field configured, the settings from the parent are ignored and used for this pool, as well as for all of its children.

For each pool, under the tab "Sequnce", a list of templates can be configured. Each row in the list has the following settings:

| Setting | Description | Type | Mandatory |
|---|---|---|---|
| Template | Template for field content which is applied | Text | Yes |
| Offset | If a sequential number is used in the template (`"%n%"`): an optional offset that is added to the sequential number | Number | No (defaults to `0`) |
| Objecttype | The objecttype to which the template is applied (only pool managed objecttypes can be selected) | Select | Yes |
| Target Field | The field in the selected objecttype which is filled with the template (only text fields can be selected) | Select | Yes |
| Only fill this field if a new object is inserted | Enable this checkbox if the template should only be applied to the field, if a new object is inserted. Disable it, if the template should also be applied if an existing object is updated | Bool | Yes |

For each row in the configured list, the template is applied if the field in the object is empty. If multiple templates are defined for the same objecttype and field, only the last template is applied.

### Template placeholders

The following placeholders can be combined with free text. When the template is applied, each occurrence of each placeholder is replaced by the corresponding value from the pool or its parent pool. If there is no value for the placeholder (for example if `"%pool.reference%"` is used and there is no reference defined for the pool), the placeholder will be kept in the resulting string. Placeholders can be used multiple times.

The sequence placeholder `"%n%"` is replaced by the next number of the sequence for the specified objecttype and field. The placeholder can be used multiple times in the template and each occurrence will be replaced by the same number.

| Placeholder | Description | Type |
|---|---|---|
| `%pool.id%` | ID of the pool | Number |
| `%pool.reference%` | Reference of the pool | Text |
| `%pool.shortname%` | Shortname of the pool | Text |
| `%pool.level%` | Level of the pool in the hierarchy (root pool: level `1`) | Number |
| `%pool.name%` | Name of the pool. The name is selected in the first database language which is configured in the base configuration | Multilanguage Text |
| `%pool.name:<lang>%` | Name of the pool in the specified language. `<lang>` needs to be replaced with the language code | Multilanguage Text |
| `%pool.parent.id%` | ID of the parent pool | Number |
| `%pool.parent.reference%` | Reference of the parent pool | Text |
| `%pool.parent.shortname%` | Shortname of the parent pool | Text |
| `%pool.parent.level%` | Level of the parent pool | Number |
| `%pool.parent.name%` | Name of the parent pool in the first database language | Multilanguage Text |
| `%pool.parent.name:<lang>%` | Name of the parent pool in the specified language | Multilanguage Text |
| `%n%` | Next sequential number for the specified objecttype and field | Number |

### Examples

* `"%pool.parent.name:de-DE% - %pool.name:de-DE% [Nr.: %n%]"`
    * `pool.parent.name:de-DE`: german name of the parent pool
    * `pool.name:de-DE`: german name of the pool
    * Examples:
        * `"Standardpool - Unterpool 1 [Nr.: 1]"`
        * `"Standardpool - Unterpool 1 [Nr.: 2]"`

* `"Pool %pool.parent.id%.%pool.id% | #%n%"`
    * Examples:
        * `"Pool 2.3 | #15"`
        * `"Pool 2.3 | #16"`
        * `"Pool 3.5 | #17"`

## FylrSequence

This class handles multiple sequences using specialized objects. This means, in the datamodel there must be an additional objecttype which stores the latest used unique sequential number. Each object represents a unique sequence.

The plugin will not check the objecttype requirements mentioned above, but they are recommended. It iterates over the objects and updates the first object where the reference matches. If the number is not set, the plugin will always start with `1`.

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
        'current_number': <?>,
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
