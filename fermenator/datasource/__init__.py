import logging

class DataSource(object):
    """
    Represents a generic key-value datastore, where the values may be arbitrary
    structures. This is an abstract class and must be implemented for specific
    types of data stores. Two main functions should be implemented for each
    subclass: :meth:`get` and :meth:`set`.
    """

    def __init__(self, name, **kwargs):
        """
        This method will be used in class implementations to configure the datasource
        object.
        """
        self.name = name
        self._config = kwargs
        self.log = logging.getLogger(
            "{}.{}.{}".format(
                self.__class__.__module__,
                self.__class__.__name__,
                name))

    def get(self, key):
        """
        Given a hierarchical key name in the form of an iterable, return an interable
        handle to the dataset found at the key. Eg::

            ds = DataSource()   # use a real datasource type here
            points = ds.get((some, nested, keyname))
            for point in points:
                print(point)

        """
        pass

    def set(self, key, value):
        """
        Set the value for a given key. Eg::

            ds = DataSource()   # use a real datasource type here
            ds.set((some, key, name), [value1, value2])

        Impelementation for this method is heavily dependent on the keystore used
        and the shape of the data being stored.
        """
        pass

    def __str__(self):
        "Returns a string representation of this object"
        return "{}(\"{}\")".format(self.__class__.__name__, self.name)

    def __repr__(self):
        "Same as :meth:`__str__`"
        return self.__str__()
