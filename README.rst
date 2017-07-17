Fermenator
==========

Fermentation management software designed with flexibility in mind. Models of
different beer styles allow custom fermentation curves to be applied. Control
relays for heating and/or cooling and monitor readings from instrumentation like
temperature, specific gravity, or pH. Out-of-the box functionality for reading
data from Google Sheets (including Brewometer/Tilt sheets), graphite, and
firebase data stores. This software was written in python and is intended to be
run from a Raspberry Pi device, but in theory could work on any machine with
a Python (3) interpreter.

Run fermenator with its command-line script, as follows::

    fermenator run

Installation
------------
Installation is possible by cloning this git repository and installing as
follows::

    git clone prairiedogbeer/fermentator
    pip install -e fermenator

Configuration
-------------
Configuration is supported through either a text file or by binding to a
configuration datastore, but in either case, a local configuration file is
required to bootstrap the basic software and tell it where to look for the
remainder of configuration. Remote configuration datastores are used to allow
users to centrally administer configuration without having to edit text files
and restart software on embedded devices every time they need to change the
temperature or name of a beer.

Fermenator looks for bootstrap configuration in the following locations, in
order, and the first file found will be used:

- .fermenator in the current working directory
- ~/.fermenator/config (a hidden directory in the user's home directory)
- /etc/fermenator/config (system-level configuration)

Configuration files are always in YaML format, and must always contain a
top-level `bootstrap` key that tells the code where to find the remainder
of configuration. There are several types of configuration datastores that can
be specified with the `type` key under `bootstrap`. Finally, any
datastore-specific configuration must be applied under the `config` sub-key.
Finally, the bootstrap configuration must be given a `name` key, which is used
in log messages to make it more obvious who is doing what in the code.

The configuration example below represents a scenario where no external
configuration datastore is used, one beer is being monitored, and a
BrewConsoleFirebaseDS datastore is read for all beer-specific instrumentation
data. The `DictionaryConfig` config datastore type is used and allows the user
to specify the entire configuration as sub-keys under `config` rather than
relying on a separate datastore for configuration::

    bootstrap:
      name: brewconsoleconfig
      type: DictionaryConfig
      config:
        version: 2017070604
        managers:
          Dark Strong:
            config:
              beer: PB0056
              active_cooling_relay: CoolingRelay1
              active_heating_relay: HeatingRelay1
              polling_frequency: 60
              active_heating: True
              active_cooling: True
        beers:
          PB0056:
            type: LinearBeer
            config:
              identifier: pfv01
              datasource: brewconsole
              original_gravity: 27.0
              final_gravity: 4.0
              start_set_point: 18
              end_set_point: 25
              tolerance: 0.3
              data_age_warning_time: 1800
        datasources:
          brewconsole:
            type: BrewConsoleFirebaseDS
            config:
              apiKey: <svc-acct-google-api-key>
              authDomain: <foo>.firebaseio.com
              databaseURL: https://<foo>.firebaseio.com
              storageBucket: <foo>.appspot.com
              serviceAccount: /path/to/a/service-acct/credentials.json
        relays:
          CoolingRelay1:
            type: Relay
            config:
              gpio_pin: 4
              duty_cycle: 0.5
              cycle_time: 600
          HeatingRelay1:
            type: Relay
            config:
              gpio_pin: 5
              duty_cycle: 0.5
              cycle_time: 1800

Based on the example above, you may be able to get a general sense of the
overall structure of the software -- bootstrap loads configuration, and
configuration loads managers, beers, datasources, and relays. Managers manage
beers and relays, beers require datasources. The details of how each of these
work and are configured is outlined further below.

The following subsections describe the different types of configuration
datastore objects and how to implement them.

FermenatorConfig
~~~~~~~~~~~~~~~~
This class represents the basic API that all of the configuration classes
further below implement. You can't use FermenatorConfig in a working setup
directly, but you can use any of the following methods with all of the config
subclasses described below, such as DictionaryConfig.

- assemble() - read all the configuration data for relays, datasources, beers,
  and managers, and assemble them into interrelated objects
- run() - start all Managers actively polling beers and check for configuration
  updates every `polling_frequency` seconds (infinite loop)
- disassemble() - shut off all managed relays and deconstruct objects, freeing
  memory

Generally speaking, if you are manually running fermenator from an interpreter
or your own python script, you need to only call `run()`, because it calls
`assemble` and `disassemble` throughout its normal routine, including on
KeyboardInterrupt or destruction.

DictionaryConfig
~~~~~~~~~~~~~~~~
As mentioned above, the DictionaryConfig datastore type simply allows you to
specify object configuration directly as python dictionary data. When a
DictionaryConfig type is specified under bootstrap configuration, fermenator
assumes that the dictionary configuration that this object requires is found
in the `config` bootstrap key, and it is passed directly into the config object
on instantiation. As such, DictionaryConfig objects are a run-time-only config
option, changing the config file after startup does not result in any changes in
runtime, so the entire program must be restarted if you change the config file.

GoogleSheetConfig
~~~~~~~~~~~~~~~~~

Google sheets are supported as simple configuration sources that allow the user
to log into a google spreadsheet remotely and turn up or down the temperature
of their beer, turn off active cooling, etc. Changes to google sheet data are
not atomic, so they are not recommended for production environments where
internally consistent configuration is critical.

The google sheet must have at least the following worksheets:

- Manager
- Beer
- DataSource
- Relay

Each worksheet should have three columns, with the first being `<type>_name`, so
for the DataSource sheet, the first column would be `datasource_name`. The
second column in each sheet should be titled 'key', and the third column should
be titled 'value'. For example, a Manger sheet may look like this:

==================  ====================  ====================
manager_name        key                   value
==================  ====================  ====================
French Saison       beer                  PB0053
French Saison       active_cooling_relay  CoolingRelay1
French Saison       active_heating_relay  HeatingRelay1
French Saison       polling_frequency     300
French Saison       active_heating        TRUE
French Saison       active_cooling        TRUE
==================  ====================  ====================

As you can see, the manager name must be repeated for every line of config
specific to that manager. Keys exactly match those in the dictionary config
example above and the Managers below. Values closely match the dictionary
example, but booleans in google sheets are all-caps.

When specifying a GoogleSheetConfig class, you must provide a config key called
`spreadsheet_id`, which contains the ID number of your google sheet (you can
pull it directly out of the URL, usually just before ``/edit``.)

The GoogleSheet base class used by GoogleSheetConfig requires a Google service
account in order to read the spreadsheet, no anonymous reading is supported at
this time. Creating a service account is out of the scope of this readme, but
you need to obtain a JSON credential file from Google and place it in a path
accessible to fermenator. Fermenator will search for the credentials file at
these locations:

- .credentials.json
- ~/.fermenator/credentials.json
- /etc/fermenator/credentials.json

The service account only requires read access to the sheet, and should be
authorized for the following scopes:

- 'https://www.googleapis.com/auth/spreadsheets.readonly',
- 'https://www.googleapis.com/auth/drive.readonly'

As with any configuration datastore, a `refresh_interval` may be supplied to
specify how often the configuration should be re-checked for updates. With
GoogleSheetConfig, the google drive API is checked for updates to the
spreadsheet. Whenever an update is found, the existing configuration and all
objects (Managers, Beers, etc) will be torn down and reconstructed based on
the latest sheet data.

Warning: GoogleSheetConfig doesn't allow for atomic changes to configuration. It is
possible that you could be half-way through updating configuration when new
objects are constructed, leading to errors in the software. It is
recommended that you update configuration in this order: Relays,
DataSources, Beers, Managers, and set fermenator to run under a manager
or shell script in an infinite loop, in case an exception causes it to
shut down. If you want a more robust remote configuration, try one of the
others below.

FirebaseConfig
~~~~~~~~~~~~~~

This class implements configuration in a simple firebase key-value datastore.
Configuration must be found under a top-level key called `config`, with a sub-
key called `fermenator`. The next level down contains keys for:

- beers
- datasources
- managers
- relays

Each of the keys above exactly match the structure found in the beginning of
this section.

FirebaseConfig also requires information about how it will access the datastore,
via the following keys in the `config` section of bootstrap::

    bootstrap:
      name: brewconsoleconfig
      type: FirebaseConfig
      config:
        apiKey: <svc-acct-google-api-key>
        authDomain: <foo>.firebaseio.com
        databaseURL: https://<foo>.firebaseio.com
        storageBucket: <foo>.appspot.com
        serviceAccount: /path/to/a/service-acct/credentials.json

You may notice that these exactly match the config keys for
BrewConsoleFirebaseDS in the example at the start of this section. You can use
the same Firebase datastore to store configuration and for beer information
(temperature, gravity, pH, etc). If you do so, you can configure the datastore
once at the bootstrap level, then set the `config` key to ``inherit`` in later
datastore configuration (which also avoids placing information such as your
apiKey into a cloud-hosted firebase).

Another point to make here is that the service account credentials file must
be specified here, rather than being automatically found on the filesystem.
This may change in the future but for now that's the way it is.

Managers
--------
Managers ask a beer, "do you require heating or cooling?", and the beer responds
with a simple "yes" or "no" to each question. One manager manages one and only
one beer.

Managers turn on and off relays for heating and cooling based on the answers
the beer gives, which are configured through the `active_cooling_relay` and
active_heating_relay` keys. Managers do not need to be configured with both
cooling and heating relays, simply omit the configuration key for one (or both)
as desired. You can also enable or disable the relays through the boolean keys,
`active_heating` and `active_cooling`, which is not very useful with a local
config file, but very useful with a central datastore that can be administered
online/remotely, where a brewmaster may want to shut off cooling entirely for
a while.

Managers run in the background and can be provided with a `polling_frequency`,
in seconds, which specifies how often they should interrogate beers about their
need of cooling or heating, and in turn, how often they should turn on and off
relays based on those answers. There is no point setting this polling frequency
at a more frequent interval than the source data is being updated at, but it
shouldn't hurt anything if you do.

Managers always try to shut down any managed relays when they shut down.

Here is an example of a complete manager configuration, which sets the manager
name (Dark Strong), and provides config. The `beer` key must match the name of
a Beer object defined elsewhere in the config::

    Dark Strong:
      config:
        beer: PB0056
        active_cooling_relay: CoolingRelay1
        active_heating_relay: HeatingRelay1
        polling_frequency: 60
        active_heating: True
        active_cooling: True

Beers
-----
All the logic about whether or
not a particular beer needs to be heated or cooled is contained within the
beer, itself, rather than in managers. This enables us to create new models
for types of beers that implement fermentation curves, diacetyl rests, etc,
and simply apply/configure them to the individual beer being scrutinized. Beers
must be provided with a datasource where they can look up their temperature,
gravity, etc. The following types of beers are currently implemented:

- AbstractBeer
- SetPointBeer
- LinearBeer

Each are described in more detail below.

AbstractBeer
~~~~~~~~~~~~
All beers descend from AbstractBeer and implement the same API as it defines.
AbstractBeer requires a name, and can be optionally provided with these config
arguments:

- data_age_warning_time: if the data read from the datastore is older than this
  (in seconds), issue a warning as a log message [default: 30 mins]
- gravity_unit: Either 'P' for Plato or 'SG' for standard gravity units.
  [default: P]
- temperature_unit: Either 'C' for Celcius or 'F' for Fahrenheit [default: C]

All beers implement the following methods:

- requires_heating(): returns True if the beer is too cold
- requires_cooling(): returns True if the beer is too hot

SetPointBeer
~~~~~~~~~~~~
This class implements a simple approach to temperature control like what you'd
find on an STC-1000. Given a set-point and a tolerance, the class tries to
keep the beer around the set-point, turning on heating and cooling as required
to keep the temp within the set point. This class has no hysteresis/smarts
about overshoot of temperature due to heating and cooling, but can be extended.

Additional configuration arguments required by this class, beyond AbstractBeer:

- datasource: the name of a datasource defined elsewhere in the config
- identifier: the string used to identify this beer at the datasource
- set_point: the floating-point set point for the beer
- tolerance: the amount of temperature drift that will be tolerated before
  heating or cooling are required [default: 0.5 degrees]

LinearBeer
~~~~~~~~~~
Based on a starting and final gravity values, as well as a starting and
an ending temperature, linearly ramp temperature on a slope.

For example, a beer starts at 25 plato and should finish at 5 plato,
for a 20 plato apparent attenuation. The brewmaster wants the beer to start
at 16 celcius and finish out at 20 celcius, for a 4 degree spread. On day 0,
with the beer at 25P, the beer will be held at 16 celcius. When the beer
reaches 20P, 1/4 of planned attenuation, it will be held at 17 celcius.
As the beer hits 15P, half way to attenuation, it will be at 18 celicus.

If the beer starts at a higher gravity than anticipated, the configured lower
starting point temperature will be applied. Same in the reverse direction. Thus,
at the end of fermentation, this class will behave more or less like a
:class:`SetPointBeer`.

Note: Nothing about this class requires that start_set_point is a lower temperature
than end_set_point. If you want to gradually cool a beer during the course of
fermentation, go for it.

This class supports the following config arguments in addition to those required
by AbstractBeer:

- original_gravity: Expected original extract/gravity in Plato or SG (depending
  on gravity_unit)
- final_gravity: Expected final gravity in Plato or SG
- start_set_point: The temperature to start the beer at (at OG/OE)
- end_set_point: Temperature the beer should finish at (at FG/AE)
- tolerance: optional, defaults to 0.5 degrees, similar to SetPointBeer

DataSources
-----------
Datasources are just what they sound like, a place where some data is stored.
In fermenator, a datasource can be used to hold configuration, or it can be a
place where some other software writes information about beers such as gravity,
temperature, or pH. At the time of this writing, fermenator does not write to
any datastores, but it was designed with writing in mind. Eventually, datastores
will hold state information about whether or not relays are on or off, if beers
are in an alarm state, etc.

Various DataSource implementations are found in fermenator, and they are
described below.

DataSource
~~~~~~~~~~
This is the abstract, base class that all datasources descend from. It defines
the basic API. The abstract DataSource object doesn't require any config
arguments, but it provides the following abstract methods:

- get()- Given a hierarchical key name in the form of an iterable, returns an
  interable handle to the dataset found at the key
- set()- Given a hierarchical key name in the form of an iterable, and a value
  for that key, sets it in the datastore

FirebaseDataSource
~~~~~~~~~~~~~~~~~~
Implementation of a DataSource that enables gets and sets against a Firebase
database. This class takes the same arguments as FirebaseConfig::

    apiKey: <svc-acct-google-api-key>
    authDomain: <foo>.firebaseio.com
    databaseURL: https://<foo>.firebaseio.com
    storageBucket: <foo>.appspot.com
    serviceAccount: /path/to/a/service-acct/credentials.json

authDomain, databaseURL and storageBucket are all easily gleaned if you look at
your Firebase database web page. apiKey and serviceAccount must match up with a
valid Google service account that has been authorized to access your Firebase
database.

Methods are the same as DataSource, `set()` is not implemented.

BrewConsoleFirebaseDS
~~~~~~~~~~~~~~~~~~~~~
This datasource implements the FirebaseDataSource with additional logic that
makes this class better for getting beer-specific data.

BrewConsoleFirebaseDS requires all of the config arguments as FirebaseDataSource
as well as the following:

- gravity_unit: 'P' for Plato or 'SG' for standard gravity units
- temperature_unit: 'C' for Celcius or 'F' for Fahrenheit

This class implements two new/important methods:

- get_gravity(): given a string that uniquely identifies a beer in the
  datastore, return the most recent gravity reading for the beer
- get_temperature(): given a string that uniquely identifies a beer in the
  datastore, return the most recent temperature reading for the beer

Both of these new methods return the data in dictionary form, like this::

    {
      'timestamp': Datetime(...),
      'temperature': 19.6,
    }

GraphiteDataSource
~~~~~~~~~~~~~~~~~~
This class implements DataSource and facilitates reading data from a graphite
web UI via the json format.

Three additional configuration arguments are supported:

- url: (the base url to graphite)
- user: (optional, password is required if user is used)
- password: (optional)

The set method is not currently implemented, since sets in graphite occur
against a completely different service (carbon), which may exist on a totally
different server. Gets work as follows::

    graphite = GraphiteDataSource(url='http://foo.bar.com')
    graphite.get((path, to, the, data))

Data is returned in reverse-time-series order as a list of dictionaries, with
keys for `timestamp` (datetime object), and whatever else was requested.

GoogleSheet
~~~~~~~~~~~
A base class designed to allow a user to get data from a google sheets
document. This class handles the authentication to the sheets API, but
does not directly implement getters and setters for the data. Subclasses
should be created for various spreadsheet formats to make getting and setting
of data easy and performant based on the type of fetches required.

All gsheet interactions require OAUTH with a client credential file. This
code is based on the concepts found here:

https://developers.google.com/sheets/api/quickstart/python

This class requires the `spreadsheet_id` config argument, which directly refers
to the id found in the spreadsheet URL.

GoogleSheet implements a few useful methods:

- get_sheet_range(): given a sheet range in the form 'Sheet1!A1:E' or similar,
  return the data in the range as a list of dicts, with row header names and
  values
- get_sheet_range_values(): same as `get_sheet_range` but without row headers
- is_spreadsheet_changed(): returns true if new sheet data is available in drive
- is_refreshed(): returns true after sheet data has been refreshed from cache
  during a read operation

BrewometerGoogleSheet
~~~~~~~~~~~~~~~~~~~~~
This is the class that specifically implements reads from Brewometer/Tilt
Google sheets. As with GoogleSheet, you must provide a `spreadsheet_id`.

This class should implement get_gravity and get_temperature similar to
BrewConsoleFirebaseDS, but it doesn't right now. Don't use this class.

Relays
------
Relays are probably the simplest object to explain. They represent real-life,
actual relays, which have two states -- on or off. Nice and simple. There are
currently two types of relay object that you may be interested in, as follows.

Relay
~~~~~
This is the base class for all relays, and doesn't actually control any hardware,
but it is useful on its own for testing
purposes. It is recommended that you try getting things up and running with
this type of relay specified, initially, then after you observe the code working
and what it would do, switch the relay type to `GPIORelay`, below. You can
specify all of the GPIORelay configuration and it won't cause errors applied to
this relay type.

Relay objects have no special configuration arguments, but they can accept
any argument you pass to them, they will just be ignored. Relays expose four
methods:

- on(): Turn on the relay
- off(): Turn off the relay
- is_on(): Return True if the relay is on
- is_off(): Return True if the relay is off

GPIORelay
~~~~~~~~~
Implement relay as a GPIO Device such as would be connected to a
Raspberry Pi. Adds support for duty cycling the relay rather than keeping
it running continuously in the on phase, which may be useful with hardware
capable of inducing rapid temperature changes in a short period of time
(where the user wants to slow down the temperature change).

These additional parameters are supported:

- gpio_pin: The GPIO pin number where a relay is connected
- duty_cycle: an optional floating point percentage of on time
- cycle_time: the total time for each duty cycle (on and off), optional
- active_high: whether sending a 1 to the gpio port should turn on the relay,
  or not (defaults to True)
