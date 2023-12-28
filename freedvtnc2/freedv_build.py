from cffi import FFI
ffibuilder = FFI()

# cdef() expects a single string declaring the C types, functions and
# globals needed to use the shared object. It must be in valid C syntax.
ffibuilder.cdef(
"""

typedef struct {
  float real;
  float imag;
} COMP;



// available speech modes
#define FREEDV_MODE_1600 0
#define FREEDV_MODE_2400A 3
#define FREEDV_MODE_2400B 4
#define FREEDV_MODE_800XA 5
#define FREEDV_MODE_700C 6
#define FREEDV_MODE_700D 7
#define FREEDV_MODE_700E 13
#define FREEDV_MODE_2020 8
#define FREEDV_MODE_2020B 16

// available data modes
#define FREEDV_MODE_FSK_LDPC 9
#define FREEDV_MODE_DATAC1 10
#define FREEDV_MODE_DATAC3 12
#define FREEDV_MODE_DATAC0 14
#define FREEDV_MODE_DATAC4 18
#define FREEDV_MODE_DATAC13 19

// Sample rates used
#define FREEDV_FS_8000 8000
#define FREEDV_FS_16000 16000

// peak (complex) sample value from Tx modulator
#define FREEDV_PEAK 16384

// Return code flags for freedv_get_rx_status() function
#define FREEDV_RX_TRIAL_SYNC 0x1  // demodulator has trial sync
#define FREEDV_RX_SYNC 0x2        // demodulator has sync
#define FREEDV_RX_BITS 0x4        // data bits have been returned
#define FREEDV_RX_BIT_ERRORS \
  0x8  // FEC may not have corrected all bit errors (not all parity checks OK)

// optional operator control of OFDM modem state machine
#define FREEDV_SYNC_UNSYNC \
  0  // force sync state machine to lose sync, and search for new sync
#define FREEDV_SYNC_AUTO 1    // falls out of sync automatically
#define FREEDV_SYNC_MANUAL 2  // fall out of sync only under operator control

#define FREEDV_VARICODE_MAX_BITS 12  // max bits for each ASCII character

// These macros allow us to disable unwanted modes at compile tine, for example
// to save memory on embedded systems or the remove need to link other
// libraries. By default we enable all modes.  Disable during compile time e.g
// -DFREEDV_MODE_1600_EN=0 will enable all but FreeDV 1600.  Or the other way
// round -DFREEDV_MODE_EN_DEFAULT=0 -DFREEDV_MODE_1600_EN=1 will enable only
// FreeDV 1600



// struct that hold state information for one freedv instance
struct freedv;

// Some modes allow extra configuration parameters
struct freedv_advanced {
  int interleave_frames;  // now unused but remains to prevent breaking API for
                          // legacy apps

  // parameters for FREEDV_MODE_FSK_LDPC
  int M;             // 2 or 4 FSK
  int Rs;            // Symbol rate Hz
  int Fs;            // Sample rate Hz
  int first_tone;    // Freq of first tone Hz
  int tone_spacing;  // Spacing between tones Hz
  char *codename;    // LDPC codename, from codes listed in ldpc_codes.c
};

// Called when text message char is decoded
typedef void (*freedv_callback_rx)(void *, char);
// Called when new text message char is needed
typedef char (*freedv_callback_tx)(void *);
typedef void (*freedv_calback_error_pattern)(void *error_pattern_callback_state,
                                             short error_pattern[],
                                             int sz_error_pattern);

// Protocol bits are packed MSB-first
// Called when a frame containing protocol data is decoded
typedef void (*freedv_callback_protorx)(void *, char *);
// Called when a frame containing protocol data is to be sent
typedef void (*freedv_callback_prototx)(void *, char *);

// Data packet callbacks
// Called when a packet has been received
typedef void (*freedv_callback_datarx)(void *, unsigned char *packet,
                                       size_t size);
// Called when a new packet can be send
typedef void (*freedv_callback_datatx)(void *, unsigned char *packet,
                                       size_t *size);

/*---------------------------------------------------------------------------*\

                                 FreeDV API functions

\*---------------------------------------------------------------------------*/

// open, close ----------------------------------------------------------------

struct freedv *freedv_open_advanced(int mode, struct freedv_advanced *adv);
struct freedv *freedv_open(int mode);
void freedv_close(struct freedv *freedv);

// Transmit -------------------------------------------------------------------

void freedv_tx(struct freedv *freedv, short mod_out[], short speech_in[]);
void freedv_comptx(struct freedv *freedv, COMP mod_out[], short speech_in[]);
void freedv_datatx(struct freedv *f, short mod_out[]);
int freedv_data_ntxframes(struct freedv *freedv);
void freedv_rawdatatx(struct freedv *f, short mod_out[],
                      unsigned char *packed_payload_bits);
void freedv_rawdatacomptx(struct freedv *f, COMP mod_out[],
                          unsigned char *packed_payload_bits);
int freedv_rawdatapreambletx(struct freedv *f, short mod_out[]);
int freedv_rawdatapreamblecomptx(struct freedv *f, COMP mod_out[]);
int freedv_rawdatapostambletx(struct freedv *f, short mod_out[]);
int freedv_rawdatapostamblecomptx(struct freedv *f, COMP mod_out[]);

// Receive -------------------------------------------------------------------

int freedv_nin(struct freedv *freedv);
int freedv_rx(struct freedv *freedv, short speech_out[], short demod_in[]);
int freedv_shortrx(struct freedv *freedv, short speech_out[], short demod_in[],
                   float gain);
int freedv_floatrx(struct freedv *freedv, short speech_out[], float demod_in[]);
int freedv_comprx(struct freedv *freedv, short speech_out[], COMP demod_in[]);
int freedv_rawdatarx(struct freedv *freedv, unsigned char *packed_payload_bits,
                     short demod_in[]);
int freedv_rawdatacomprx(struct freedv *freedv,
                         unsigned char *packed_payload_bits, COMP demod_in[]);

// Helper functions
// -------------------------------------------------------------------

int freedv_codec_frames_from_rawdata(struct freedv *freedv,
                                     unsigned char *codec_frames,
                                     unsigned char *rawdata);
int freedv_rawdata_from_codec_frames(struct freedv *freedv,
                                     unsigned char *rawdata,
                                     unsigned char *codec_frames);
unsigned short freedv_gen_crc16(unsigned char *bytes, int nbytes);
void freedv_pack(unsigned char *bytes, unsigned char *bits, int nbits);
void freedv_unpack(unsigned char *bits, unsigned char *bytes, int nbits);
unsigned short freedv_crc16_unpacked(unsigned char *bits, int nbits);
int freedv_check_crc16_unpacked(unsigned char *unpacked_bits, int nbits);

// Set parameters ------------------------------------------------------------

void freedv_set_callback_txt(struct freedv *freedv, freedv_callback_rx rx,
                             freedv_callback_tx tx, void *callback_state);
void freedv_set_callback_protocol(struct freedv *freedv,
                                  freedv_callback_protorx rx,
                                  freedv_callback_prototx tx,
                                  void *callback_state);
void freedv_set_callback_data(struct freedv *freedv,
                              freedv_callback_datarx datarx,
                              freedv_callback_datatx datatx,
                              void *callback_state);
void freedv_set_test_frames(struct freedv *freedv, int test_frames);
void freedv_set_test_frames_diversity(struct freedv *freedv,
                                      int test_frames_diversity);
void freedv_set_squelch_en(struct freedv *freedv, bool squelch_en);
void freedv_set_snr_squelch_thresh(struct freedv *freedv,
                                   float snr_squelch_thresh);
void freedv_set_clip(struct freedv *freedv, bool val);
void freedv_set_total_bit_errors(struct freedv *freedv, int val);
void freedv_set_total_bits(struct freedv *freedv, int val);
void freedv_set_total_bit_errors_coded(struct freedv *freedv, int val);
void freedv_set_total_bits_coded(struct freedv *freedv, int val);
void freedv_set_total_packets(struct freedv *freedv, int val);
void freedv_set_total_packet_errors(struct freedv *freedv, int val);
void freedv_set_callback_error_pattern(struct freedv *freedv,
                                       freedv_calback_error_pattern cb,
                                       void *state);
void freedv_set_varicode_code_num(struct freedv *freedv, int val);
void freedv_set_data_header(struct freedv *freedv, unsigned char *header);
void freedv_set_carrier_ampl(struct freedv *freedv, int c, float ampl);
void freedv_set_sync(struct freedv *freedv, int sync_cmd);
void freedv_set_verbose(struct freedv *freedv, int verbosity);
void freedv_set_tx_bpf(struct freedv *freedv, int val);
void freedv_set_tx_amp(struct freedv *freedv, float amp);
void freedv_set_ext_vco(struct freedv *f, int val);
void freedv_set_phase_est_bandwidth_mode(struct freedv *f, int val);
void freedv_set_eq(struct freedv *f, bool val);
void freedv_set_frames_per_burst(struct freedv *f, int framesperburst);
void freedv_passthrough_gain(struct freedv *f, float g);
int freedv_set_tuning_range(struct freedv *freedv, float val_fmin,
                            float val_fmax);

// Get parameters
// -------------------------------------------------------------------------

struct MODEM_STATS;

int freedv_get_version(void);
char *freedv_get_hash(void);
int freedv_get_mode(struct freedv *freedv);
void freedv_get_modem_stats(struct freedv *freedv, int *sync, float *snr_est);
void freedv_get_modem_extended_stats(struct freedv *freedv,
                                     struct MODEM_STATS *stats);
int freedv_get_test_frames(struct freedv *freedv);

int freedv_get_speech_sample_rate(struct freedv *freedv);
int freedv_get_n_speech_samples(struct freedv *freedv);
int freedv_get_n_max_speech_samples(struct freedv *freedv);

int freedv_get_modem_sample_rate(struct freedv *freedv);
int freedv_get_modem_symbol_rate(struct freedv *freedv);
int freedv_get_n_max_modem_samples(struct freedv *freedv);
int freedv_get_n_nom_modem_samples(struct freedv *freedv);
int freedv_get_n_tx_modem_samples(struct freedv *freedv);
int freedv_get_n_tx_preamble_modem_samples(struct freedv *freedv);
int freedv_get_n_tx_postamble_modem_samples(struct freedv *freedv);

// bit error rate stats
int freedv_get_total_bits(struct freedv *freedv);
int freedv_get_total_bit_errors(struct freedv *freedv);
int freedv_get_total_bits_coded(struct freedv *freedv);
int freedv_get_total_bit_errors_coded(struct freedv *freedv);
int freedv_get_total_packets(struct freedv *freedv);
int freedv_get_total_packet_errors(struct freedv *freedv);

int freedv_get_rx_status(struct freedv *freedv);
void freedv_get_fsk_S_and_N(struct freedv *freedv, float *S, float *N);

int freedv_get_sync(struct freedv *freedv);
int freedv_get_sync_interleaver(struct freedv *freedv);

// access to speech codec states
struct FSK *freedv_get_fsk(struct freedv *f);
struct CODEC2 *freedv_get_codec2(struct freedv *freedv);

int freedv_get_bits_per_codec_frame(struct freedv *freedv);
int freedv_get_bits_per_modem_frame(struct freedv *freedv);
int freedv_get_sz_error_pattern(struct freedv *freedv);
int freedv_get_protocol_bits(struct freedv *freedv);







// #define MODEM_STATS_NC_MAX 50
// #define MODEM_STATS_NR_MAX 320
// #define MODEM_STATS_ET_MAX 8
// #define MODEM_STATS_EYE_IND_MAX 160
// #define MODEM_STATS_NSPEC 512
// #define MODEM_STATS_MAX_F_HZ 4000
// #define MODEM_STATS_MAX_F_EST 4

// struct MODEM_STATS {
//   int Nc;
//   float snr_est; /* estimated SNR of rx signal in dB (3 kHz noise BW)  */
//   COMP rx_symbols[MODEM_STATS_NR_MAX][MODEM_STATS_NC_MAX + 1];
//   /* latest received symbols, for scatter plot          */
//   int nr;             /* number of rows in rx_symbols                       */
//   int sync;           /* demod sync state                                   */
//   float foff;         /* estimated freq offset in Hz                        */
//   float rx_timing;    /* estimated optimum timing offset in samples         */
//   float clock_offset; /* Estimated tx/rx sample clock offset in ppm         */
//   float sync_metric;  /* number between 0 and 1 indicating quality of sync  */
//   int pre, post;      /* preamble/postamble det counters for burst data     */
//   int uw_fails;       /* Failed to detect Unique word (burst data)          */

//   /* FSK eye diagram traces */
//   /* Eye diagram plot -- first dim is trace number, second is the trace idx */
//   float rx_eye[MODEM_STATS_ET_MAX][MODEM_STATS_EYE_IND_MAX];
//   int neyetr;   /* How many eye traces are plotted */
//   int neyesamp; /* How many samples in the eye diagram */

//   /* optional for FSK modems - est tone freqs */

//   float f_est[MODEM_STATS_MAX_F_EST];

//   /* Buf for FFT/waterfall */

//   float fft_buf[2 * MODEM_STATS_NSPEC];
//   void *fft_cfg;
// };

// void modem_stats_open(struct MODEM_STATS *f);
// void modem_stats_close(struct MODEM_STATS *f);
// void modem_stats_get_rx_spectrum(struct MODEM_STATS *f, float mag_spec_dB[],
//                                  COMP rx_fdm[], int nin);

"""
)

# set_source() gives the name of the python extension module to
# produce, and some C source code as a string.  This C code needs
# to make the declarated functions, types and globals available,
# so it is often just the "#include".
ffibuilder.set_source("_freedv_cffi",
"""
     #include "freedv_api.h"   // the C header of the library
""",
     libraries=['codec2'],
     include_dirs = [ "/usr/include/codec2/", "/usr/local/include/codec2/", "/opt/homebrew/include/codec2/"],
     library_dirs = ["/lib", "/usr/lib", "/usr/local/lib/", "/opt/homebrew/lib/"]
     )   # library name, for the linker

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)