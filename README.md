# fylr-plugin-sequence

This plugin allows the automatic filling of configurable empty fields in inserted objects based on sequential numbers.

The automatic filling of empty fields can be configured [in a general way](#base-configuration) per objecttype and field, or for pool managed objects, with more complex patterns based on [pool settings](#pool-settings).

## Requirements

### Objecttype to store the sequences

To store the current value of different sequences, this plugin uses a specialized objecttype. This objecttype **must be added to the datamodel**, and must fullfil these following requirements:

* **text** field for the reference:
    * this field stores a **(unique) identifier** so the sequence can be identified by this **reference**
    * it should have a `NOT NULL` constraint, so no sequence object without a reference can exist
    * it should have a `UNIQUE` constraint, so each sequence can be identified (the plugin will use the first object that fits)

* **integer** field:
    * this field stores the latest used **sequential number**
    * it should have a `NOT NULL` constraint, so no sequence object without a number can exist
    * it must **not** have a `UNIQUE` constraint, because the sequential number could collide with other unrelated sequences

The objecttype should be as simple as possible. It is not necessary to enable pool or tag management, or make it hierarchical or enable it to be included in the main search. 

The objecttype must have a single simple mask which allows reading and editing of both these fields. 
 
### Rights management 

The plugin uses the fylr API to update the sequence and the saved objects. To authenticate the necessary requests, the plugin uses the same user session as the user which is currently logged in. 

This means that the user (or group in which the user is) needs the necessary *read* and *write* rights on the special sequence objecttype and on the mask. Missing rights will cause the plugin to fail.

## Setup

### Base Configuration

#### Settings for the sequence objecttype

The specialized sequence objecttype must be selected in the base config so the plugin can use it.

* **Objecttype**
    * select the objecttype that is used to store the sequences

* **Reference Field**
    * text field
    * this field stores a **(unique) identifier** so the sequence can be identified by this **reference**

* **Number Field**
    * integer field
    * this field stores the latest used **sequential number**

#### Settings for the updated fields in objects

For each objecttype one or more fields can be defined which are checked by the plugin if they are empty. If the field is empty, the plugin will use the template to format a string that contains the sequential number and update the field. The selected fields must be text fields.

* **Objecttype**
    * select the objecttype to be updated

* **Text Field**
    * select the text field to be updated

* **Template for field content**
    * insert the template for the text that will be generated
    * the template must comply to the specific format below

* **Field in object to specify the sequence**
    * optional field in the current object to be added to the sequence reference.
    * if this field is specified, a separate sequence is kept per value of this field
    * this makes it possible to set different sequential numbers depending on field values in the object

* **Start offset of the sequence**
    * optional integer value to add to the sequential number

* **Only fill this field if a new object is inserted**
    * if activated, this option causes updated objects (version > 1) to be skipped by the plugin
    * activate this option if you only want to fill fields once when the object is created

#### Template format

The template must contain a placeholder for the sequential number, as well as an optional prefix and suffix. The placeholder must be in the [`printf` format style of python3](https://docs.python.org/3/library/stdtypes.html#printf-style-string-formatting) and must be compatible to format an integer value.

If a value from the field is used to specify the sequence, this value can also be used in the template. The placeholder for this value is `%field%`.

Please keep in mind, that only a **single, unnamed placeholder** can be used, otherwise an internal formatting error will be caused.

Some examples for useful placeholders inside the template are:

| Template         | Description                                                                                  | Example     |
|------------------|----------------------------------------------------------------------------------------------|-------------|
| `%d`             | Simple number                                                                                | `13`        |
| `%04d`           | Number with four trailing zeros                                                              | `0027`      |
| `%08x`           | Hexadecimal number with eight trailing zeros                                                 | `00000BB9`  |
| `[%field%] %04d` | Value from the optional field of the sequence (e.g. `AB`) und Number with four leading zeros | `[AB] 0342` |

Please note that it is not necessary to include `"` in the template definition.

### Pool Settings

Empty fields in objects can also be filled by using templates based on pool settings. When an object is inserted/updated, based on the pool of the object, the configured templates of the pool are applied.

A template is a text with a combination of fixed text and [template placeholders](#template-placeholders). The placeholders are replaced by values of the pool and the pools parent, as well as sequential numbers.

The pool settings are inherited from parent pools. This means, if there is a template configured for a specific pair of objecttype and field, all children of the pool also get this template. If a child pool has a template for objecttype and field configured, the settings from the parent are ignored and used for this pool, as well as for all of its children.

For each pool, under the tab "Sequnce", a list of templates can be configured. Each row in the list has the following settings:

| Setting                                          | Description                                                                                                                                                                                | Type   | Mandatory            |
|--------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------|----------------------|
| Template                                         | Template for field content which is applied                                                                                                                                                | Text   | Yes                  |
| Offset                                           | If a sequential number is used in the template (`"%n%"`): an optional offset that is added to the sequential number                                                                        | Number | No (defaults to `0`) |
| Objecttype                                       | The objecttype to which the template is applied (only pool managed objecttypes can be selected)                                                                                            | Select | Yes                  |
| Target Field                                     | The field in the selected objecttype which is filled with the template (only text fields can be selected)                                                                                  | Select | Yes                  |
| Only fill this field if a new object is inserted | Enable this checkbox if the template should only be applied to the field, if a new object is inserted. Disable it, if the template should also be applied if an existing object is updated | Bool   | Yes                  |

For each row in the configured list, the template is applied if the field in the object is empty. If multiple templates are defined for the same objecttype and field, only the last template is applied.

#### Template placeholders

The following placeholders can be combined with free text. When the template is applied, each occurrence of each placeholder is replaced by the corresponding value from the pool or its parent pool. If there is no value for the placeholder (for example if `%pool.reference%` is used and there is no reference defined for the pool), the placeholder will be kept in the resulting string. Placeholders can be used multiple times.

The sequence placeholder `%n%` is replaced by the next number of the sequence for the specified objecttype and field. The placeholder can be used multiple times in the template and each occurrence will be replaced by the same number.

| Placeholder                 | Description                                                                                                         | Type               |
|-----------------------------|---------------------------------------------------------------------------------------------------------------------|--------------------|
| `%pool.id%`                 | ID of the pool                                                                                                      | Number             |
| `%pool.reference%`          | Reference of the pool                                                                                               | Text               |
| `%pool.shortname%`          | Shortname of the pool                                                                                               | Text               |
| `%pool.level%`              | Level of the pool in the hierarchy (root pool: level `1`)                                                           | Number             |
| `%pool.name%`               | Name of the pool. The name is selected in the first database language which is configured in the base configuration | Multilanguage Text |
| `%pool.name:<lang>%`        | Name of the pool in the specified language. `<lang>` needs to be replaced with the language code                    | Multilanguage Text |
| `%pool.parent.id%`          | ID of the parent pool                                                                                               | Number             |
| `%pool.parent.reference%`   | Reference of the parent pool                                                                                        | Text               |
| `%pool.parent.shortname%`   | Shortname of the parent pool                                                                                        | Text               |
| `%pool.parent.level%`       | Level of the parent pool                                                                                            | Number             |
| `%pool.parent.name%`        | Name of the parent pool in the first database language                                                              | Multilanguage Text |
| `%pool.parent.name:<lang>%` | Name of the parent pool in the specified language                                                                   | Multilanguage Text |
| `%n%`                       | Next sequential number for the specified objecttype and field                                                       | Number             |

#### Examples

* `%pool.parent.name:de-DE% - %pool.name:de-DE% [Nr.: %n%]`
    * `pool.parent.name:de-DE`: german name of the parent pool
    * `pool.name:de-DE`: german name of the pool
    * Examples:
        * `"Standardpool - Unterpool 1 [Nr.: 1]"`
        * `"Standardpool - Unterpool 1 [Nr.: 2]"`

* `Pool %pool.parent.id%.%pool.id% | #%n%`
    * Examples:
        * `"Pool 2.3 | #15"`
        * `"Pool 2.3 | #16"`
        * `"Pool 3.5 | #17"`

## Usage

The plugin is executed in the background whenever one of the objecttypes which have been configured in the base configuration or in a pool is inserted or updated. If one of the configured fields is empty, the plugin increments the sequence for the field and uses the template to fill the field.

This is done after saving, and will not be visible in the editor. It will be visible after after the object has been inserted or updated in the database, and has been reindexed.

### Known problems and errors

#### Fields are not updated

If fields are empty after saving, check the configuration and make sure that the correct sequence objecttype and fields are selected. Also check the templates, to make sure they have the valid format. It is also necessary that the current session has the necessary *write* rights, and that the fields are also writable in the mask that the user is allowed to use.

#### Errors during saving

If the sequence can not be updated, the saving of the object in the editor will fail. The plugin will display an error message in the frontend. The most common errors will mention missing rights (with a http error code of 403), in which case the rights management needs to be checked and updated. 

Other errors will give information about api errors, or even internal errors in the plugin. In any case, the complete error will be displayed with all available information.
