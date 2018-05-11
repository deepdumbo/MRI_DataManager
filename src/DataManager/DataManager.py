import os
import matplotlib
matplotlib.use('TkAgg')
from matplotlib import pyplot as plt
from src.Utilities.utilities import (
	extract_NIFTI,
	read_CSV,
	write_data,
	get_FigShare_filemap,
	get_BRRATS_filemap,
)
from src.DataManager.PreProcessData import *
from src.DataManager.FeatureExtractor import *
import numpy as np
import h5py

ADNI = 'ADNI'
FIG_SHARE = 'FigShare'
BRATS = 'BRATS'

class DataManager(object):
	""" Organization of the data

	The class contains a dictionary with the metadata of all the datasets that we will be using.
	It is a means to organize and aggregate data from different sources. It is also used as a wrapper to
	fetch the data from these different sources and compile them into a uniform dataset.

	Attrs:
		dataCollection (dictionary): Contains the metadata for all the datasets stored indexed by 
		                             the name of the dataset. The metadata should be organized as
		                             a pandas dataframe. The unique key should be the subject ID.
		data_splits (dictionary): Contains the train/validation/test indices for each of the 
		                          datasets in dataCollection based on the subject ID.
		information (dictionary): Contains information about the dataset 
								  ADNI:
			                          [0]: filepath to the metadata
			                          [1]: filepath to the data*
			                          [2]: indices to extract in the metadata
			                          [3]: key for the index in the dataset

			                          * filepath (string): Filepath to the root folder where datasets stored
			                   		  Requried file structure
			                      		- filepath
			                         		- ADNI (folder)
			                            		- MRI data (folder): contains the NIFTI files
			                            		- dataset_metadata.csv: file comtaining metadata
			                      FIG_SHARE:
			                      	  directory: path to the directory containing FigShare data
			                      	  num_slices: total number of MRI slices
	"""

	# List of datasets currently supported
	supported_datasets = [ADNI, FIG_SHARE, BRATS]

	def __init__(self, filepath, datasets = None):
		for dataset in datasets:
			if dataset not in self.supported_datasets:
				raise NameError('Unsupported dataset: {}'.format(dataset))

		self.dataCollection = {}
		self.data_splits = {}

		# Information about the datasets as a dictionary
		self.information = {
			ADNI: {
				'metadata_filepath': filepath + 'ADNI/dataset_metadata.csv', 
				'data_filepath':     filepath + r'ADNI/MRI data/', 
				'cols':              [0, 3, 4, 6],
				'key':               'Subject'},
			FIG_SHARE: {
				'data_filepath': 	 filepath + r'/1512427/',
				'key': 				 'Patient ID'
				},
			BRATS: {
				'data_filepath': 	 filepath + r'/BRATS/',
				'key': 				 'Subject'
				}
			}

		# Add the datasets that are listed to the data collection
		self.add_datasets(datasets)

	def add_datasets(self, datasets):
		""" Add new datasets to the dataCollection dictionary

		Args:
			datasets (list of strings): List of strings with the name of all the datasets
										to add to the collection.
		"""
		for dataset in datasets:
			if dataset == ADNI:
				filepath = self.information[dataset]['metadata_filepath']
				indices = self.information[dataset]['cols']
				# Add dataset to the collection
				self.dataCollection.update({str(dataset): read_CSV(filepath, indices)})
			elif dataset == FIG_SHARE:
				pid_slice_files_map = get_FigShare_filemap(
										self.information[dataset]['data_filepath'])
				self.dataCollection.update({str(dataset): pid_slice_files_map})
			elif dataset == BRATS:
				subject_id_files_map = get_BRRATS_filemap(self.information[dataset]['data_filepath'])
				self.dataCollection.update({str(dataset): subject_id_files_map})

			key = self.information[dataset]['key']
			self.train_validate_test_split(dataset, column_header=key)

	def train_validate_test_split(self, dataset, column_header, train_percent=.6, valid_percent=.2, seed=None):
		"""Splits up the index associated with the dataset into a train/validation/test set
		
		Adds a new train/validation/test set to the data_splits dictionary.

		Args:
			dataset (string): Name of the dataset in question
			column_header (string): Name of the column header with the unique key
			train_percent (float): percentage of the data to reserve for training [0, 1]
			valid_percent (float): percentage of the data for validation [0, 1]
			seed (int): means by which to generate the random shuffling of the data
		"""
		if not seed is None: np.random.seed(seed)
		
		data = self.dataCollection[dataset][column_header]
		perm = np.random.permutation(data)
		m = len(data)

		# Get the split indices
		train_end = int(train_percent * m)
		valid_end = int(valid_percent * m) + train_end
		train, valid, test = perm[:train_end], perm[train_end:valid_end], perm[valid_end:]

		self.data_splits.update({str(dataset): [train, valid, test]})

	def compile_dataset(self, params):
		""" Extracts the features for the datasets and compiles them into a .h5 database

		Args:
			dataset (string): the dataset from which to extract features. 
			params (dictionary): contains all the options the user wants for
								 extracting the desired features.
		Datasets:
			${split_name}_${feature_name}: array of feature_data
			split_name: train, validation, test
			feature_name: image, k_space, label (optional)

		"""
		dataset = params['dataset']
		filepath = self.information[dataset]['data_filepath']
		# Extract the features
		featureExtractor = FeatureExtractor(params)

		#options = {}
		#if dataset == FIG_SHARE:
		#	options = {'subject_id_files_map': self.dataCollection[dataset]['pid_slice_files_map']}

		with h5py.File('experiments/'+params['database_name']+'.h5', 'w') as hf:
			for param in params:
				print(param, ': ', params[param])
				hf.attrs[param] = params[param]

			for ix, data_split in enumerate(['train', 'validation', 'test']):
				print('extracting {} data from {} ...'.format(data_split, dataset))
				subjects = self.data_splits[dataset][ix]
				hf.attrs['subjects_'+data_split] = subjects
				f = featureExtractor.extract_features(subjects[0:2], dataset, 
													  filepath, metadata=self.dataCollection[dataset])
				for ix, data in enumerate(f):
					for d in data:
						print(data_split+'_'+d)
						hf.create_dataset(data_split+'_'+d+'_'+str(ix), data=data[d])

	def get_data_collection(self):
		""" Returns the data collection containing all the metadata.
		"""
		return self.dataCollection

	def get_data(self, dataset, key):
		""" Returns the metadata from the data collection for a particular dataset.

		Args:
			dataset: the dataset from whiich to return the metadata
			key: the column information which is to be returned
		"""
		if dataset in self.dataCollection:
			if key in self.dataCollection[dataset].columns:
				return self.dataCollection[dataset][key]

	def get_keys(self, dataset):
		"""Returns a list of keys available for a given dataset''s metadata

		Args:
			dataset: the dataset for which to get all the keys.
		"""
		if dataset in self.dataCollection:
			return self.dataCollection[dataset].keys()

	def view_subject(self, dataset, subject_id, slice_ix = 0.5, scan_type = 'T1'):
		""" View a image of the slice obtained from a subject

		Args:
			dataset (str): the dataset from which to extract the image
			subject_id (int): the unique index of the subject
			slice_ix (float): the slice to show
			scan_type (str): The type of scan to show ('T1' or 'T2')
		"""
		filepath = self.information[dataset][1]

		# Get the T1-weighted MRI image from the datasource and the current subject_id
		data, aff, hdr = extract_NIFTI(filepath, subject_id, scan_type)
		img = extract_slice(data, slice_ix)
		plt.imshow(img.T, cmap = 'gray')
		plt.colorbar()
		plt.show()
