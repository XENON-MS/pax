import pax.datastructure as ds

from pax import plugin, utils
from pax.micromodels import fields as mm_fields
import tables


class HDF5Output(plugin.OutputPlugin):

    """Use PyTables to write HDF5 output

    HDF5 is a hierarchical data structure used extensively in astrophysics, and
    other scientific fields.  The PyTables module allows us to easily create
    these files.  The structure of the file is that there are tables and rows.
    A table could be an event table, where each row is an event and column a
    variable associated with that event (e.g., start time).  Similarly, we have
    tables of peaks and reconstructed quantities that refer to values in other
    tables.  For example, every peak has an event index, which is the row
    associated to it in the event table.
    """

    hdf5_column = {
        mm_fields.StringField:  tables.StringCol(32),
        mm_fields.IntegerField: tables.Int64Col(),
        mm_fields.FloatField:   tables.Float64Col(),
        # Numpy array fields not supported?
    }

    def startup(self):
        self.h5_file = tables.open_file(self.config['output_name'], 'w')

        self.hdf5_fields = {}

        # Need dummy instances here... bit wonky
        internal_classes = [utils.empty_event(),
                            ds.Peak(),
                            ds.ReconstructedPosition()]

        for ic in internal_classes:
            fields = {}
            for field_name, field_instance in ic.get_fields_data().items():
                hd5_column = self.hdf5_column.get(field_instance.__class__, None)
                if hd5_column is not None:
                    fields[field_name] = self.hdf5_column.get(field_instance.__class__, None)

            name = ic.__class__.__name__

            self.hdf5_fields[name] = fields

        self.hdf5_fields['Peak']['event_number'] = self.hdf5_fields['Event']['event_number']
        self.hdf5_fields['ReconstructedPosition']['event_number'] = self.hdf5_fields['Event']['event_number']

        # Filters are used for compression.  We use the blosc algorithm.
        compression_filter = tables.Filters(complevel=9, complib='blosc')

        self.tables = {}
        self.rows = {}

        # There is a 'table' for every object type.  Therefore, there is an
        # event table, peak table, and reconstructed position table.
        for key, value in self.hdf5_fields.items():
            table = type('%s_table' % key.lower(),
                         (tables.IsDescription,),
                         value)

            self.tables[key] = self.h5_file.create_table('/',
                                                         '%s_table' % key.lower(),
                                                         table,
                                                         filters=compression_filter)
            self.rows[key] = self.tables[key].row

    def write_event(self, event):
        self.log.debug('HDF5ing event')

        # Convert the event to a Python dictionary to make it easier to
        # serialize to HDF5
        event_dict = event.to_dict()

        # Construct event table
        for key, val in self.hdf5_fields['Event'].items():
            if isinstance(val, tables.Col):
                self.rows['Event'][key] = event_dict[key]

        self.rows['Event'].append()

        # TODO: construct channel peaks table

        # Construct peak table
        for peak in event_dict['peaks']:
            peak = peak.to_dict()
            for key, val in self.hdf5_fields['Peak'].items():
                if isinstance(val, tables.Col):
                    if key == 'event_number':
                        self.rows['Peak'][key] = event_dict[key]
                    else:
                        self.rows['Peak'][key] = peak[key]
            self.rows['Peak'].append()

            # Construct reconstructed position table
            for track in peak['reconstructed_positions']:
                track = track.to_dict()

                for key, val in self.hdf5_fields['ReconstructedPosition'].items():
                    if isinstance(val, tables.Col):
                        if key == 'event_number':
                            self.rows['ReconstructedPosition'][key] = event_dict[key]
                        else:
                            self.rows['ReconstructedPosition'][key] = track[key]

                self.rows['ReconstructedPosition'].append()

    def shutdown(self):
        for table_name, table in self.tables.items():
            try:
                table.flush()
            except AttributeError as e:
                self.log.error("Arcane error in flushing HDF5 table %s on shutdown of HDF5Output. " % table_name +
                               "May be related to running multiple Processor's with clean_shutdown=False?\n"
                               )
                raise e

        self.h5_file.close()
