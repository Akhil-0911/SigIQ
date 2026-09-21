/* Small shared app state, plain JS object -- no framework/store library. */
const AppState = {
  uploadedFile: null,     // { file_id, filename, format, metadata }
  configOptions: null,    // { modulations, fec_types, deinterleaving_types, iq_dtypes }
  jobId: null,
  result: null,
};
