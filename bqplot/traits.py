# Copyright 2015 Bloomberg Finance L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

r"""

============
Traits Types
============

.. currentmodule:: bqplot.traits

.. autosummary::
   :toctree: _generate/

   Date
   PandasDataFrame
   PandasSeries
"""

from traitlets import Instance, TraitError, TraitType, Undefined

import traittypes as tt
import numpy as np
import pandas as pd
import warnings
import datetime as dt


class Date(TraitType):

    """
    A datetime trait type.

    Converts the passed date into a string format that can be used to
    construct a JavaScript datetime.
    """

    def validate(self, obj, value):
        try:
            if isinstance(value, dt.datetime):
                return value
            if isinstance(value, dt.date):
                return dt.datetime(value.year, value.month, value.day)
            if np.issubdtype(np.dtype(value), np.datetime64):
                # TODO: Fix this. Right now, we have to limit the precision
                # of time to microseconds because np.datetime64.astype(datetime)
                # returns date values only for precision <= 'us'
                value_truncated = np.datetime64(value, 'us')
                return value_truncated.astype(dt.datetime)
        except Exception:
            self.error(obj, value)
        self.error(obj, value)

    def __init__(self, default_value=dt.datetime.today(), **kwargs):
        args = (default_value,)
        self.default_value = default_value
        kwargs.setdefault('to_json', Date.to_json)
        kwargs.setdefault('from_json', Date.from_json)
        super(Date, self).__init__(args=args, **kwargs)

    @staticmethod
    def to_json(value, obj=None):
        if value is None:
            return value
        else:
            return value.strftime('%Y-%m-%dT%H:%M:%S.%f')

    @staticmethod
    def from_json(value, obj=None):
        if value:
            return dt.datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%f')
        else:
            return value

def array_from_json(value, obj=None):
    if value is not None:
        if value.get('values') is not None:
            dtype = {
                'date': np.datetime64,
                'float': np.float64
            }.get(value.get('type'), object)
            return np.asarray(value['values'], dtype=dtype)

def array_to_json(a, obj=None):
    if a is not None:
        if np.issubdtype(a.dtype, np.float):
            # replace nan with None
            dtype = a.dtype
            a = np.where(np.isnan(a), None, a)
        elif a.dtype in (int, np.int64):
            dtype = 'float'
            a = a.astype(np.float64)
        elif np.issubdtype(a.dtype, np.datetime64):
            dtype = 'date'
            a = a.astype(np.str).astype('object')
            for x in np.nditer(a, flags=['refs_ok'], op_flags=['readwrite']):
                # for every element in the nd array, forcing the conversion into
                # the format specified here.
                temp_x = pd.to_datetime(x.flatten()[0])
                if pd.isnull(temp_x):
                    x[...] = None
                else:
                    x[...] = temp_x.to_pydatetime().strftime(
                        '%Y-%m-%dT%H:%M:%S.%f')
        else:
            dtype = a.dtype
        return dict(values=a.tolist(), type=str(dtype))
    else:
        return dict(values=a, type=None)

array_serialization = dict(to_json=array_to_json, from_json=array_from_json)

def convert_to_date(array, fmt='%m-%d-%Y'):
    # If array is a np.ndarray with type == np.datetime64, the array can be
    # returned as such. If it is an np.ndarray of dtype 'object' then conversion
    # to string is tried according to the fmt parameter.

    if(isinstance(array, np.ndarray) and np.issubdtype(array.dtype, np.datetime64)):
        # no need to perform any conversion in this case
        return array
    elif(isinstance(array, list) or (isinstance(array, np.ndarray) and array.dtype == 'object')):
        return_value = []
        # Pandas to_datetime handles all the cases where the passed in
        # data could be any of the combinations of
        #            [list, nparray] X [python_datetime, np.datetime]
        # Because of the coerce=True flag, any non-compatible datetime type
        # will be converted to pd.NaT. By this comparision, we can figure
        # out if it is date castable or not.
        if(len(np.shape(array)) == 2):
            for elem in array:
                temp_val = pd.to_datetime(
                    elem, errors='coerce', box=False, infer_datetime_format=True)
                temp_val = elem if (
                    temp_val[0] == np.datetime64('NaT')) else temp_val
                return_value.append(temp_val)
        elif(isinstance(array, list)):
            temp_val = pd.to_datetime(
                array, errors='coerce', box=False, infer_datetime_format=True)
            return_value = array if (
                temp_val[0] == np.datetime64('NaT')) else temp_val
        else:
            temp_val = pd.to_datetime(
                array, errors='coerce', box=False, infer_datetime_format=True)
            temp_val = array if (
                temp_val[0] == np.datetime64('NaT')) else temp_val
            return_value = temp_val
        return return_value
    elif(isinstance(array, np.ndarray)):
        warnings.warn("Array could not be converted into a date")
        return array

def array_squeeze(trait, value):
    if 1 in value.shape and len(value.shape) > 1:
        value = np.squeeze(value)
    return value

def array_dimension_bounds(mindim=0, maxdim=np.inf):
    def validator(trait, value):
        dim = len(value.shape)
        if dim < mindim or dim > maxdim:
            raise TraitError('Dimension mismatch for trait %s of class %s: expected an \
            array of dimension comprised in interval [%s, %s] and got an array of shape %s'\
            % (trait.name, trait.this_class, mindim, maxdim, value.shape))
        return value
    return validator


class PandasDataFrame(Instance):

    """A pandas Dataframe trait type.

    The json representation is an array of dicts which is amenable for
    consumption by JavaScript. also note that index name is ignored and when
    deserializing will use the 'index' attribute as an index for the df. This
    means if the data frame cannot have a column called 'index'.
    """
    klass = pd.DataFrame
    info_text = 'a pandas DataFrame'

    def __init__(self, *args, **kwargs):
        default_value = kwargs.pop('default_value', None)
        # The first entry in args should be the `klass`. If it is None, self.klass
        # is assigned as the klass. The second entry should be a tuple whose
        # first element is passed to the default constructor of the klass.
        # Hence, we should set the following as the args
        if len(args) == 0:
            new_args = (None, (default_value,))
        else:
            new_args = args
        super(PandasDataFrame, self).__init__(*new_args, **kwargs)
        self.tag(to_json=self._to_json, from_json=self._from_json)

    def _from_json(self, value, obj=None):
        if value is not None and value != []:
            df = pd.DataFrame(value)
            df = df.set_index(self.index_name)
            df.index.name = None
        else:
            df = pd.DataFrame()
        return df

    def _to_json(self, df, obj=None):
        if df is not None:
            # Name of the index column
            self.index_name = df.index.name
            if self.index_name is None:
                # If the index is not named, reset_index() names the column 'index'
                self.index_name = 'index'
            return df.reset_index().to_dict(orient='records')
        else:
            return []

    def set(self, obj, value):
        new_value = self._validate(obj, value)
        try:
            old_value = obj._trait_values[self.name]
        except KeyError:
            old_value = self.default_value

        obj._trait_values[self.name] = new_value
        try:
            if new_value is not None:
                silent = new_value.equals(old_value)
            else:
                silent = bool(new_value == old_value)
        except:
            # if there is an error in comparing, default to notify
            silent = False
        if silent is not True:
            # we explicitly compare silent to True just in case the equality
            # comparison above returns something other than True/False
            obj._notify_trait(self.name, old_value, new_value)

    def validate(self, obj, value):
        value = super(PandasDataFrame, self).validate(obj, value)
        if self.get_metadata('lexsort'):
            if isinstance(value.columns, pd.MultiIndex):
                value = value.sortlevel(0, axis=1)
        return value


class PandasSeries(Instance):

    """A pandas Series trait type.

    The json representation is an array of dicts which is amenable for
    consumption by JavaScript. Also note that index name is ignored and when
    deserializing will use the 'index' attribute as an index for the df. This
    means if the data frame has a column called 'index'.
    """
    klass = pd.Series
    info_text = 'a pandas series'

    def __init__(self, *args, **kwargs):
        default_value = kwargs.pop('default_value', None)
        # This is the same as for PandasDataFrame.
        # The first entry in args should be the `klass`. If it is None, self.klass
        # is assigned as the klass. The second entry should be a tuple whose
        # first element is passed to the default constructor of the klass.
        # Hence, we should set the following as the args.
        if len(args) == 0:
            new_args = (None, (default_value,))
        else:
            new_args = args
        super(PandasSeries, self).__init__(*new_args, **kwargs)
        self.tag(to_json=self._to_json, from_json=self._from_json)

    def _from_json(self, value, obj=None):
        return pd.Series(value)

    def _to_json(self, s, obj=None):
        return s.to_dict()
