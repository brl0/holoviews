import numpy as np
from collections import OrderedDict

import param

from .ndmapping import Dimension
from .views import View, Overlay, Annotation, Stack

def find_minmax(lims, olims):
    """
    Takes (a1, a2) and (b1, b2) as input and returns
    (np.min(a1, b1), np.max(a2, b2)). Used to calculate
    min and max values of a number of items.
    """

    limzip = zip(list(lims), list(olims), [np.min, np.max])
    return tuple([float(fn([l, ol])) for l, ol, fn in limzip])



class DataLayer(View):
    """
    DataLayer is a 2D View type used to hold data indexed
    by an x-dimension and y-dimension. The data held within
    the DataLayer is a numpy array of shape (n, 2).

    DataLayer objects are sliceable along the X dimension
    allowing easy selection of subsets of the data.
    """

    dimensions = param.List(default=[Dimension('X')])

    legend_label = param.String(default="", doc="Legend labels")

    value = param.ClassSelector(class_=(str, Dimension), default='Y')

    def __init__(self, data, **kwargs):
        settings = {}
        if isinstance(data, DataLayer):
            settings = dict(data.get_param_values())
            data = data.data
        elif isinstance(data, Stack) or (isinstance(data, list) and data
                                         and isinstance(data[0], DataLayer)):
            data, settings = self._process_stack(data)

        data = list(data)
        if len(data) and not isinstance(data, np.ndarray):
            data = np.array(data)

        self._xlim = None
        self._ylim = None
        settings.update(kwargs)
        super(DataLayer, self).__init__(data, **settings)


    def _process_stack(self, stack):
        """
        Base class to process a DataStack to be collapsed into a DataLayer.
        Should return the data and parameters of reduced View.
        """
        data = []
        for v in stack:
            data.append(v.data)
        return np.concatenate(data), dict(v.get_param_values())


    def sample(self, **samples):
        """
        Allows sampling of DataLayer objects using the default
        syntax of providing a map of dimensions and sample pairs.
        """
        sample_data = {}
        for sample_dim, samples in samples.items():
            if not isinstance(samples, list): samples = [samples]
            for sample in samples:
                if sample_dim in self.dimension_labels:
                    sample_data[sample] = self[sample]
                else:
                    self.warning('Sample dimension %s invalid on %s'
                                 % (sample_dim, type(self).__name__))
        return Table(sample_data, **dict(self.get_param_values()))


    def reduce(self, label_prefix='', **reduce_map):
        """
        Allows collapsing of DataLayer objects using the supplied map of
        dimensions and reduce functions.
        """
        reduced_data = {}
        value = self.value(' '.join([label_prefix, self.value.name]))
        for dimension, reduce_fn in reduce_map.items():
            data = reduce_fn(self.data[:, 1])
            reduced_data[value] = data
        return Table(reduced_data, label=self.label, title=self.title)


    def __getitem__(self, slc):
        """
        Implements slicing or indexing of the data by the data x-value.
        If a single element is indexed reduces the DataLayer to a single
        Scatter object.
        """
        if slc is ():
            return self
        if isinstance(slc, slice):
            start, stop = slc.start, slc.stop
            xvals = self.data[:, 0]
            start_idx = np.abs((xvals - start)).argmin()
            stop_idx = np.abs((xvals - stop)).argmin()
            return self.__class__(self.data[start_idx:stop_idx, :],
                                  **dict(self.get_param_values()))
        else:
            slc = np.where(self.data[:, 0] == slc)
            sample = self.data[slc, :]
            return Scatter(sample, **dict(self.get_param_values()))


    def __mul__(self, other):
        if isinstance(other, DataStack):
            items = [(k, self * v) for (k, v) in other.items()]
            return other.clone(items=items)
        elif isinstance(self, DataOverlay):
            if isinstance(other, DataOverlay):
                overlays = self.data + other.data
            else:
                overlays = self.data + [other]
        elif isinstance(other, DataOverlay):
            overlays = [self] + other.data
        elif isinstance(other, DataLayer):
            overlays = [self, other]
        else:
            raise TypeError('Can only create an overlay of DataViews.')

        return DataOverlay(overlays)


    @property
    def stack_type(self):
        return DataStack


    @property
    def cyclic_range(self):
        if self.dimensions[0].cyclic:
            return self.dimensions[0].range[1]
        else:
            return None


    @property
    def xlabel(self):
        return self.dimensions[0].pprint_label


    @property
    def ylabel(self):
        return str(self.value)


    @property
    def xlim(self):
        if self._xlim:
            return self._xlim
        elif isinstance(self, Overlay):
            return None
        elif self.cyclic_range is not None:
            return (0, self.cyclic_range)
        else:
            x_vals = self.data[:, 0]
            return (float(min(x_vals)), float(max(x_vals)))


    @xlim.setter
    def xlim(self, limits):
        xmin, xmax = limits
        xlim = self.xlim
        if self.cyclic_range and not isinstance(self, Overlay):
            self.warning('Cannot override the limits of a cyclic dimension')
        elif xlim is None or (xmin <= xlim[0] and xmax >= xlim[1]):
            self._xlim = (xmin, xmax)
        elif not isinstance(self, Overlay):
            self.warning('Applied x-limits need to be inclusive '
                         'of all data.')


    @property
    def ylim(self):
        if self._ylim:
            return self._ylim
        elif isinstance(self, Overlay):
            return None
        y_vals = self.data[:, 1]
        return (float(min(y_vals)), float(max(y_vals)))


    @ylim.setter
    def ylim(self, limits):
        ymin, ymax = limits
        ylim = self.ylim
        if ylim is None or (ymin <= ylim[0] and ymax >= ylim[1]):
            self._ylim = (ymin, ymax)
        elif not isinstance(self, Overlay):
            self.warning('Applied y-limits need to be inclusive '
                         'of all data.')


    @property
    def lbrt(self):
        if self.xlim is None: return None, None, None, None
        l, r = self.xlim
        b, t = self.ylim
        return l, b, r, t



class Scatter(DataLayer):
    """
    Scatter is a simple 1D View, which gets displayed as a number of
    disconnected points.
    """


class Curve(DataLayer):
    """
    Curve is a simple 1D View of points and therefore assumes the data is
    ordered.
    """

    def __init__(self, data, **kwargs):
        super(Curve, self).__init__(data, **kwargs)

    def stack(self):
        stack = DataStack(None, dimensions=[self.xlabel], title=self.title+' {dims}')
        for idx in range(len(self.data)):
            x = self.data[0]
            if x in stack:
                stack[x].data.append(self.data[0:idx])
            else:
                stack[x] = Curve(self.data[0:idx])
        return stack


class Bars(DataLayer):
    """
    A bar is a simple 1D View of bars, which assumes that the data is sorted by
    x-value and there are no gaps in the bars.
    """

    def __init__(self, data, width=None, **kwargs):
        super(Bars, self).__init__(data, **kwargs)
        self._width = width

    @property
    def width(self):
        if self._width == None:
            return set(np.diff(self.data[:, 1]))[0]
        else:
            return self._width



class Histogram(DataLayer):
    """
    Histogram contains a number of bins, which are defined by the upper
    and lower bounds of their edges and the computed bin values.
    """

    title = param.String(default='{label} {type}')

    value = param.ClassSelector(class_=(str, Dimension), default='Frequency')

    def __init__(self, values, edges=None, **kwargs):
        self.values, self.edges, settings = self._process_data(values, edges)
        settings.update(kwargs)
        super(Histogram, self).__init__([], **settings)
        self.data = (self.values, self.edges)


    def _process_data(self, values, edges):
        """
        Ensure that edges are specified as left and right edges of the
        histogram bins rather than bin centers.
        """
        settings = {}
        if isinstance(values, DataLayer):
            values = values.data[:, 0]
            edges = values.data[:, 1]
            settings = dict(values.get_param_values())
        elif isinstance(values, np.ndarray) and len(values.shape) == 2:
            values = values[:, 0]
            edges = values[:, 1]
        else:
            values = np.array(values)
            edges = np.array(edges, dtype=np.float)

        if len(edges) == len(values):
            widths = list(set(np.diff(edges)))
            if len(widths) == 1:
                width = widths[0]
            else:
                raise Exception('Centered bins have to be of equal width.')
            edges -= width/2.
            edges = np.concatenate([edges, [edges[-1]+width]])
        return values, edges, settings


    def __getitem__(self, slc):
        raise NotImplementedError('Slicing and indexing of histograms currently not implemented.')


    def sample(self, **samples):
        raise NotImplementedError('Cannot sample a Histogram.')


    def reduce(self, **dimreduce_map):
        raise NotImplementedError('Reduction of Histogram not implemented.')


    @property
    def xlim(self):
        if self.cyclic_range is not None:
            return (0, self.cyclic_range)
        else:
            return (min(self.edges), max(self.edges))


    @property
    def ylim(self):
        return (min(self.values), max(self.values))



class DataOverlay(DataLayer, Overlay):
    """
    A DataOverlay can contain a number of DataLayer objects, which are to be
    overlayed on one axis. When adding new DataLayers to the DataOverlay
    it ensures the DataLayers have the same x- and y-label and recomputes the
    axis limits.
    """

    def __init__(self, overlays, **kwargs):
        Overlay.__init__(self, [], **kwargs)
        self._xlim = None
        self._ylim = None
        self.set(overlays)


    def __getitem__(self, ind):
        return Overlay.__getitem__(self, ind)


    def add(self, layer):
        if isinstance(layer, Annotation): pass
        elif not len(self):
            self.xlim = layer.xlim
            self.ylim = layer.ylim
            self.dimensions = layer.dimensions
            self.value = layer.value
            self.label = layer.label
        else:
            self.xlim = layer.xlim if self.xlim is None else find_minmax(self.xlim, layer.xlim)
            self.ylim = layer.ylim if self.xlim is None else find_minmax(self.ylim, layer.ylim)
            if layer.dimension_labels != self.dimension_labels:
                raise Exception("DataLayers must share common dimensions.")
        self.data.append(layer)


    @property
    def cyclic_range(self):
        return self[0].cyclic_range if len(self) else None



class DataStack(Stack):
    """
    A DataStack can hold any number of DataLayers indexed by a list of
    dimension values. It also has a number of properties, which can find
    the x- and y-dimension limits and labels.
    """

    data_type = (DataLayer, Annotation)

    overlay_type = DataOverlay


    @property
    def xlabel(self):
        return self.last.xlabel


    @property
    def ylabel(self):
        return self.last.ylabel


    @property
    def xlim(self):
        xlim = self.last.xlim
        for data in self.values():
            xlim = find_minmax(xlim, data.xlim)
        return xlim


    @property
    def ylim(self):
        ylim = self.last.ylim
        for data in self.values():
            ylim = find_minmax(ylim, data.ylim)
        return ylim


    @property
    def lbrt(self):
        l, r = self.xlim
        b, t = self.ylim
        return float(l), float(b), float(r), float(t)



class Table(View):
    """
    A tabular view type to allow convenient visualization of either a
    standard Python dictionary or an OrderedDict. If an OrderedDict is
    used, the headings will be kept in the correct order.
    """

    @property
    def stack_type(self):
        return TableStack

    def __init__(self, data, **kwargs):
        super(Table, self).__init__(data=data, **kwargs)

        # Assume OrderedDict if not a vanilla Python dict
        headings = self.data.keys()
        if type(self.data) == dict: headings = sorted(headings)
        self.heading_map = OrderedDict([(el, str(el)) for el in headings])


    def sample(self, samples=None):
        if callable(samples):
            sampled_data = dict([item for item in self.data.items() if samples(item)])
        else:
            sampled_data = dict([(k, v) for k, v in self.data.items() if k in samples])
        return self.clone(sampled_data)


    def reduce(self, **reduce_map):
        reduced_data = {}
        for reduce_label, reduce_fn in reduce_map.items():
            data = reduce_fn(self.data.values())
            reduced_data[reduce_label] = data
        return self.clone(reduced_data)


    @property
    def rows(self):
        return len(self.heading_map)


    @property
    def cols(self):
        return 2


    def __getitem__(self, heading):
        """
        Get the value associated with the given heading (key).
        """
        if heading is ():
            return self
        if heading not in self.heading_map:
            raise IndexError("%r not in available headings." % heading)
        return self.data[heading]


    def cell_value(self, row, col):
        """
        Get the stored value for a given row and column indices.
        """
        if col > 1:
            raise Exception("Only two columns available in a Table.")
        elif row >= self.rows:
            raise Exception("Maximum row index is %d" % len(self.headings)-1)
        elif col == 0:
            return list(self.heading_map.values())[row]
        else:
            heading = list(self.heading_map.keys())[row]
            return self.data[heading]


    def heading_values(self):
        return list(self.heading_map.keys())


    def heading_names(self):
        return list(self.heading_map.values())


    def cell_type(self, row, col):
        """
        Returns the cell type given a row and column index. The common
        basic cell types are 'data' and 'heading'.
        """
        if col == 0:  return 'heading'
        else:         return 'data'



class TableStack(Stack):
    """
    A TableStack may hold any number of TableViews indexed by a list
    of dimension values. It also allows the values of a particular
    cell to be sampled by name across any valid dimension.
    """
    _type = Table

    _type_map = None

    def sample(self, samples):
        """
        Samples the Table elements in the Stack by the provided samples.
        If multiple samples are provided the samples are laid out side
        by side in a GridLayout. By providing an x_dimension the individual
        samples are joined up into a Curve.
        """
        return self.clone([(k, view.sample(samples)) for k, view in self.items()])



    def reduce(self, **reduce_map):
        """
        Reduces the Tables in the Stack using the provided the function
        provided in the reduce_tuple (reduced_label, reduce_fn).

        If an x_dimension is provided the reduced values are joined up
        to a Curve. By default reduces all values in a Table but using
        a match_fn a subset of elements in the Tables can be selected.
        """
        return self.clone([(k, view.reduce(reduce_map)) for k, view in self.items()])


    def collate(self, collate_dim):
        """
        Collate splits out the specified dimension and joins the samples
        in each of the split out Stacks into Curves. If there are multiple
        entries in the Table it will lay them out into a Grid.
        """
        nested_stack = self.split_dimensions([collate_dim])
        new_dimensions = [d for d in self.dimensions if d.name != collate_dim]
        collate_dim = self.dim_dict[collate_dim]

        # Generate a DataStack for every entry in the table
        stack_fn = lambda: DataStack(**dict(self.get_param_values(), dimensions=new_dimensions))
        entry_dims = OrderedDict([(str(k), k) for k in self.last.data.keys()])
        stacks = OrderedDict([(entry, stack_fn()) for entry in entry_dims])
        for new_key, collate_stack in nested_stack.items():
            curve_data = OrderedDict([(k, []) for k in entry_dims.keys()])
            # Get the x- and y-values for each entry in the Table
            xvalues = [k for k in collate_stack.keys()]
            for x, table in collate_stack.items():
                for label, value in table.data.items():
                    curve_data[str(label)].append(value)

            # Get data from table
            table = collate_stack.last
            table_dimensions = table.dimensions
            table_title = ' ' + table.title
            table_label = table.label

            # Generate curves with correct dimensions
            for label, yvalues in curve_data.items():
                settings = dict(dimensions=[collate_dim])
                label = entry_dims[label]
                if len(table_dimensions):
                    if not isinstance(label, tuple): label = (label,)
                    title = ', '.join([d.pprint_value(label[idx]) for idx, d in
                                      enumerate(table_dimensions)]) + table_title
                    settings.update(value=table.value, label=table_label, title=title)
                else:
                    settings.update(value=entry_dims[label], label=table_label)
                stacks[str(label)][new_key] = Curve(zip(xvalues, yvalues), **settings)

        # If there are multiple table entries, generate grid
        stack_data = stacks.values()
        stack_grid = stack_data[0]
        for stack in stack_data[1:]:
            stack_grid += stack
        return stack_grid


    def heading_values(self):
        return self.last.heading_values() if len(self) else []


    def heading_names(self):
        return self.last.heading_names() if len(self) else []


    def _item_check(self, dim_vals, data):

        if self._type_map is None:
            self._type_map = dict((str(k), type(v)) for (k,v) in data.data.items())

        if set(self._type_map.keys()) != set([str(k) for k in data.data.keys()]):
            raise AssertionError("All TableViews in a TableStack must have"
                                 " a common set of headings.")

        for k, v in data.data.items():
            key = str(k) # Cast dimension to string
            if key not in self._type_map:
                self._type_map[key] = None
            elif type(v) != self._type_map[key]:
                self._type_map[key] = None

        super(TableStack, self)._item_check(dim_vals, data)




__all__ = list(set([_k for _k,_v in locals().items() if isinstance(_v, type) and
                    (issubclass(_v, Stack) or issubclass(_v, View))]))
