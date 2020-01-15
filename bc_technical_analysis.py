# -*- coding: utf-8 -*-
import math
import sympy
import ta
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import gridspec
from mpl_finance import candlestick_ohlc
from quant import bc_util as util
from scipy.stats import linregress
try:
  from scipy.signal import find_peaks
except Exception as e:
  print(e)



# ================================================ Basic calculation ================================================ #
# drop na values for dataframe
def dropna(df):
  """
  Drop rows with "Nans" values

  :param df: original dfframe
  :returns: dfframe with Nans dropped
  :raises: none
  """
  df = df[df < math.exp(709)]  # big number
  df = df[df != 0.0]
  df = df.dropna()
  return df

# fill na values for dataframe
def fillna(series, fill_value=0):
  """
  Fill na value for a series with specific value
  :param series: series to fillna
  :param fill_value: the value to replace na values
  :returns: series with na values filled
  :raises: none
  """
  series.replace([np.inf, -np.inf], np.nan).fillna(fill_value)
  return series

# get max/min in 2 values
def get_min_max(x1, x2, f='min'):
  """
  Get Max or Min value from 2 values

  :param x1: value 1
  :param x2: value 2
  :param f: which one do you want: max/min
  :returns: max or min value
  :raises:
  """    
  if not np.isnan(x1) and not np.isnan(x2):
    if f == 'max':
      return max(x1, x2)
    elif f == 'min':
      return min(x1, x2)
    else:
      raise ValueError('"f" variable value should be "min" or "max"')
  else:
    return np.nan    
    
# filter index that meet conditions
def filter_idx(df, condition):
  """
  # filter index that meet conditions
  :param df: dataframe to search
  :param condition: dictionary of conditions
  :returns: dictionary of index that meet corresponding conditions
  :raises: None
  """
  # target index
  result = {}
  for c in condition.keys():
    result[c] = df.query(condition[c]).index

  # other index
  other_idx = df.index
  for i in result.keys():
    other_idx = [x for x in other_idx if x not in result[i]]
  result['other'] = other_idx

  return result



# ================================================ Core calculation ================================================= #   
# remove invalid records from downloaded stock data
def preprocess_stock_data(df, interval, print_error=True):
  '''
  Preprocess downloaded data

  :param df: downloaded stock data
  :param interval: interval of the downloaded data
  :param print_error: whether print error information or not
  :returns: preprocessed dataframe
  :raises: None
  '''    
  # drop duplicated rows, keep the first
  df = util.remove_duplicated_index(df=df, keep='first')

  # if interval is week, keep data until the most recent monday
  if interval == 'week' and df.index.max().weekday() != 0:
    df = df[:-1].copy()

  # process NA and 0 values
  max_idx = df.index.max()
  na_cols = []
  zero_cols = []
  error_info = ''
        
  # check whether 0 or NaN values exists in the latest record
  for col in df.columns:
    if df.loc[max_idx, col] == 0:
      zero_cols.append(col)
    if np.isnan(df.loc[max_idx, col]):
      na_cols.append(col)
    
  # process NaN values
  if len(na_cols) > 0:
    error_info += 'NaN values found in '
    for col in na_cols:
      error_info += '{col}, '.format(col=col)
  df = df.dropna()
    
  # process 0 values
  if len(zero_cols) > 0:
    error_info += '0 values found in '
    for col in zero_cols:
      error_info += '{col}, '.format(col=col)
    df = df[:-1].copy()

  # print error information
  if print_error and len(error_info) > 0:
    error_info += '[{date}]'.format(date=max_idx.date())
    print(error_info)
  
  return df
  
# calculate certain selected ta indicators
def calculate_ta(df, sec_code):
  """
  calculate selected ta features for dataframe
  :param df: original dataframe with hlocv features
  :param sec_code: sec_code 
  :returns: dataframe with ta features
  :raises: None
  """
  try:
    # price change rate
    phase = 'cal_change_rate' 
    df = cal_change_rate(df=df, target_col='Close')

    # ichimoku
    phase = 'cal_ichimoku' 
    df = add_ichimoku_features(df=df)
      
    # KAMA
    phase = 'cal_kama'  
    df = add_kama_features(df=df)

    # ADX
    phase = 'cal_adx'  
    df = add_adx_features(df=df)

    # EOM
    phase = 'cal_eom'  
    df = add_eom_features(df=df)

    # KST
    phase = 'cal_kst'  
    df = add_kst_features(df=df)
    
    # RSI
    phase = 'cal_rsi'  
    df = add_rsi_features(df=df)
    
    # BBL
    phase = 'cal_bbl'  
    df = add_bb_features(df=df)

    # sec_code
    phase = 'sec_code'
    df['sec_code'] = sec_code

  except Exception as e:
    print(phase, e)

  return df

# analyze calculated ta indicators
def calculate_ta_derivative(df, signal_indicators=['kama', 'ichimoku', 'adx', 'eom', 'kst'], trend_indicators=['adx_trend', 'eom_diff', 'kst_diff'], n_slope=3):
  """
  adding derived features such as trend, momentum, etc.
  :param df: dataframe with several ta features
  :param n_slope: period for calculating slopes
  :returns: dataframe with extra fetures
  :raises: Exception 
  """
  try:    
    # calculate days since signal triggered
    phase = 'cal_number_of_days_since_signal_triggered'

    # replace signal value [b/s/n] with [1/-1/0]
    for indicator in signal_indicators:
      signal_col = '{indicator}_signal'.format(indicator=indicator)
      day_col = '{indicator}_day'.format(indicator=indicator)
      df[day_col] = df[signal_col].replace({'n':0, 'b':1, 's':-1})
    
    # go through each signal
    idx_list = df.index.tolist()
    for i in range(1, len(idx_list)):
      current_idx = idx_list[i]
      previous_idx = idx_list[i-1]

      for indicator in signal_indicators:
        day_col = '{indicator}_day'.format(indicator=indicator)
        current_day = df.loc[current_idx, day_col]
        previous_day = df.loc[previous_idx, day_col]
        
        if previous_day>0 and current_day == 0:
          df.loc[current_idx, day_col] = previous_day + 1
        elif previous_day<0 and current_day == 0:
          df.loc[current_idx, day_col] = previous_day - 1
    
    # summary of signal trigger
    phase = 'summarize_overall_signals'
    df['overall_signal'] = ''
    df['overall_signal_value'] = 0
    for indicator in signal_indicators:
      day_col = '{indicator}_day'.format(indicator=indicator)
      tmp_day = df[[day_col]].astype(float)

      # buy signal just triggered
      b_idx = tmp_day.query('{d} == 1'.format(d=day_col)).index
      if len(b_idx)> 0:
        df.loc[b_idx, 'overall_signal'] += 'b'
        df.loc[b_idx, 'overall_signal_value'] += 1

      # buy signal triggered more than 2 days
      pb_idx = tmp_day.query('{d} > 1'.format(d=day_col)).index
      if len(pb_idx)> 0:        
        df.loc[pb_idx, 'overall_signal'] += '+'
        df.loc[pb_idx, 'overall_signal_value'] += 0.1

      # sell signal just triggered
      s_idx = tmp_day.query('{d} == -1'.format(d=day_col)).index
      if len(s_idx)> 0:         
        df.loc[s_idx, 'overall_signal'] += 's'
        df.loc[s_idx, 'overall_signal_value'] += -1

      # sell signal triggered more than 2 days
      ps_idx = tmp_day.query('{d} < -1'.format(d=day_col)).index
      if len(ps_idx)> 0:
        df.loc[ps_idx, 'overall_signal'] += '-'
        df.loc[ps_idx, 'overall_signal_value'] += -0.1

      # no signal triggered yet
      n_idx = tmp_day.query('{d} == 0'.format(d=day_col)).index
      if len(n_idx)> 0:
        df.loc[n_idx, 'overall_signal'] += ' '
        df.loc[n_idx, 'overall_signal_value'] += 0
    
    # calculate trend slope
    phase = 'cal_trend_slope'
    for index, row in df.iterrows():
      for i in trend_indicators:
        slope_name = i.split('_')[0] + '_slope'
        df.loc[index, slope_name] = linear_fit(df=df[: index], target_col=i, periods=n_slope)['slope']
    
    # calculate overall trend and momentum 
    df['overall_trend'] = 0 # [-3, -1, 1, 3]
    df['overall_momentum'] = 0 # [-3, -1, 1, 3]
    df['overall_momentum_value'] = 0 
    for i in trend_indicators:
      slope_name = i.split('_')[0] + '_slope'
      df['overall_trend'] +=  ((df[i] > 0).astype(int) + -1*(df[i] < 0).astype(int))
      df['overall_momentum'] += ((df[slope_name] > 0).astype(int) + -1*(df[slope_name] < 0).astype(int))
      df['overall_momentum_value'] += 0.333 * df[slope_name]

  except Exception as e:
    print(phase, e)

  return df

# calculate ta signal
def calculate_ta_signal(df):
  """
  :param df: dataframe with ta features and derived features for calculating signals
  :raturns: dataframe with signal
  :raises: None
  """

  df = df.copy()
  df['signal'] = 'n'
  
  # buy signal
  buy_idx = df.query('(kama_day == 1 or adx_day == 1) and (overall_trend == 3) or (overall_momentum == 3)').index
  if len(buy_idx) > 0:
    df.loc[buy_idx, 'signal'] = 'b'

  # sell signal
  sell_idx = df.query('(overall_signal_value <= -1) and ((overall_trend == -3) or (overall_momentum == -3))').index
  if len(sell_idx) > 0:  
    df.loc[sell_idx, 'signal'] = 's'

  # filter senstive signals
  none_trend_idx = df.query('adx < 20').index
  if len(none_trend_idx) > 0:
    df.loc[none_trend_idx, 'signal'] = 'n'

  df = remove_redundant_signal(df=df)

  return df

# visualize ta indicators
def visualize_ta(df, sec_code, args={}):
  """
  visualize ta indicators
  :param df: dataframe with ta indicators
  :param args: visualizing arguments
  :returns: None
  :raises: Exception
  """
  try:
    # visualize 
    if args.get('visualize'):
      phase = 'visulize'
      plot_multiple_indicators(
        df=df, title=sec_code,
        args=args.get('args'), 
        start=args.get('start'), 
        show_image=args.get('show_image'), 
        save_image=args.get('save_image'), 
        save_path=args.get('save_path'))

  except Exception as e:
    print(phase, e)

# post-process calculation results
def postprocess_ta_result(df, keep_columns, drop_columns):
  """
  Postprocess downloaded data

  :param df: dataframe with ta features and ta derived features
  :param keep_columns: columns to keep for the final result
  :param drop_columns: columns to drop for the final result
  :param watch_columns: list of indicators to keep watching
  :returns: postprocessed dataframe
  :raises: None
  """     
  # reset index(as the index(date) of rows are all the same)
  df = df.reset_index()
  df['notes'] = ''

  # whether the price is in a corresponding high position
  high_idx = df.query('(Close > kama_fast > kama_slow) and kama_day > 5').index
  df.loc[high_idx, 'notes'] += '高位'

  # whether the trend or momentum is downwarding
  down_idx = df.query('(overall_trend < 0 and overall_momentum < 0) or (overall_momentum_value < 0)').index
  none_empty_idx = df.query('notes != ""').index
  df.loc[[x for x in down_idx if x in none_empty_idx], 'notes'] += ','
  df.loc[down_idx, 'notes'] += '向下'

  # whether the momentum is very weak
  weak_idx = df.query('0< overall_momentum_value < 0.1').index
  none_empty_idx = df.query('notes != ""').index
  df.loc[[x for x in weak_idx if x in none_empty_idx], 'notes'] += ','
  df.loc[weak_idx, 'notes'] += '向上无力'
  
  # overbuy
  ob_idx = df.query('bb_signal == "s" or rsi_signal =="s"').index
  none_empty_idx = df.query('notes != ""').index
  df.loc[[x for x in ob_idx if x in none_empty_idx], 'notes'] += ','
  df.loc[ob_idx, 'notes'] += '超买'
  
  # oversell
  os_idx = df.query('bb_signal == "b" or rsi_signal =="b"').index
  none_empty_idx = df.query('notes != ""').index
  df.loc[[x for x in os_idx if x in none_empty_idx], 'notes'] += ','
  df.loc[os_idx, 'notes'] += '超卖'

  # sec_code that could be ignored
  x_idx = df.query('notes != ""').index
  df.loc[x_idx, 'overall_signal'] = 'x' + df.loc[x_idx, 'overall_signal']

  # rename columns, keep 3 digits
  df = df[list(keep_columns.keys())].rename(columns=keep_columns).round(3)
    
  # drop columns
  df = df.drop(drop_columns, axis=1)
  
  # sort by operation and sec_code
  df = df.sort_values(['信号', '代码'], ascending=[True, True])
  
  return df



# ================================================ Rolling windows ================================================== #
# simple moving window
def sm(series, periods, fillna=False):
  """
  Simple Moving Window

  :param series: series to roll
  :param periods: size of the moving window
  :param fillna: make the min_periods = 0
  :returns: a rolling window with window size 'periods'
  :raises: none
  """  
  if fillna:  
    return series.rolling(window=periods, min_periods=0)
  return series.rolling(window=periods, min_periods=periods)

# exponential moving window
def em(series, periods, fillna=False):
  """
  Exponential Moving Window

  :param series: series to roll
  :param periods: size of the moving window
  :param fillna: make the min_periods = 0
  :returns: an exponential weighted rolling window with window size 'periods'
  :raises: none
  """  
  if fillna:
    return series.ewm(span=periods, min_periods=0)
  return series.ewm(span=periods, min_periods=periods)  


 
# ================================================ Change calculation =============================================== #
# calculate change of a column in certain period
def cal_change(df, target_col, periods=1, add_accumulation=True, add_prefix=False, drop_na=False):
  """
  Calculate change of a column with a sliding window
  
  :param df: original dfframe
  :param target_col: change of which column to calculate
  :param periods: calculate the change within the period
  :param add_accumulation: wether to add accumulative change in a same direction
  :param add_prefix: whether to add prefix for the result columns (when there are multiple target columns to calculate)
  :param drop_na: whether to drop na values from dataframe:
  :returns: dataframe with change rate columns
  :raises: none
  """
  # copy dateframe
  df = df.copy()

  # set prefix for result columns
  prefix = ''
  if add_prefix:
    prefix = target_col + '_'

  # set result column names
  change_col = prefix + 'change'
  acc_change_col = prefix + 'acc_change'
  acc_change_count_col = prefix + 'acc_change_count'

  # calculate change within the period
  df[change_col] = df[target_col].diff(periods=periods)
  
  # calculate accumulative change in a same direction
  if add_accumulation:
    df[acc_change_col] = 0
    df.loc[df[change_col]>=0, acc_change_count_col] = 1
    df.loc[df[change_col]<0, acc_change_count_col] = -1
  
    # go through each row, add values with same symbols (+/-)
    idx = df.index.tolist()
    for i in range(1, len(df)):
      current_idx = idx[i]
      previous_idx = idx[i-1]
      current_change = df.loc[current_idx, change_col]
      previous_acc_change = df.loc[previous_idx, acc_change_col]
      previous_acc_change_days = df.loc[previous_idx, acc_change_count_col]

      if previous_acc_change * current_change > 0:
        df.loc[current_idx, acc_change_col] = current_change + previous_acc_change
        df.loc[current_idx, acc_change_count_col] += previous_acc_change_days
      else:
        df.loc[current_idx, acc_change_col] = current_change

  # drop NA values
  if drop_na:        
    df.dropna(inplace=True)

  return df 

# calculate change rate of a column in certain period
def cal_change_rate(df, target_col, periods=1, add_accumulation=True, add_prefix=False, drop_na=False):
  """
  Calculate change rate of a column with a sliding window
  
  :param df: original dfframe
  :param target_col: change rate of which column to calculate
  :param periods: calculate the change rate within the period
  :param add_accumulation: wether to add accumulative change rate in a same direction
  :param add_prefix: whether to add prefix for the result columns (when there are multiple target columns to calculate)
  :param drop_na: whether to drop na values from dataframe:
  :returns: dataframe with change rate columns
  :raises: none
  """
  # copy dfframe
  df = df.copy()
  
  # set prefix for result columns
  prefix = ''
  if add_prefix:
    prefix = target_col + '_'

  # set result column names
  rate_col = prefix + 'rate'
  acc_rate_col = prefix + 'acc_rate'
  acc_day_col = prefix + 'acc_day'

  # calculate change rate within the period
  df[rate_col] = df[target_col].pct_change(periods=periods)
  
  # calculate accumulative change rate in a same direction
  if add_accumulation:
    df[acc_rate_col] = 0
    df.loc[df[rate_col]>=0, acc_day_col] = 1
    df.loc[df[rate_col]<0, acc_day_col] = -1
  
    # go through each row, add values with same symbols (+/-)
    idx = df.index.tolist()
    for i in range(1, len(df)):
      current_idx = idx[i]
      previous_idx = idx[i-1]
      current_rate = df.loc[current_idx, rate_col]
      previous_acc_rate = df.loc[previous_idx, acc_rate_col]
      previous_acc_days = df.loc[previous_idx, acc_day_col]

      if previous_acc_rate * current_rate > 0:
        df.loc[current_idx, acc_rate_col] = current_rate + previous_acc_rate
        df.loc[current_idx, acc_day_col] += previous_acc_days
      else:
        df.loc[current_idx, acc_rate_col] = current_rate

  if drop_na:        
    df.dropna(inplace=True) 

  return df



# ================================================ Signal processing ================================================ #
# calculate signal that generated from 2 lines crossover
def cal_crossover_signal(df, fast_line, slow_line, result_col='signal', pos_signal='b', neg_signal='s', none_signal='n'):
  """
  Calculate signal generated from the crossover of 2 lines
  When fast line breakthrough slow line from the bottom, positive signal will be generated
  When fast line breakthrough slow line from the top, negative signal will be generated 

  :param df: original dffame which contains a fast line and a slow line
  :param fast_line: columnname of the fast line
  :param slow_line: columnname of the slow line
  :param result_col: columnname of the result
  :param pos_signal: the value of positive signal
  :param neg_siganl: the value of negative signal
  :param none_signal: the value of none signal
  :returns: series of the result column
  :raises: none
  """
  df = df.copy()

  # calculate the distance between fast and slow line
  df['diff'] = df[fast_line] - df[slow_line]
  df['diff_prev'] = df['diff'].shift(1)

  # get signals from fast/slow lines cross over
  df[result_col] = none_signal
  pos_idx = df.query('diff > 0 and diff_prev < 0').index
  neg_idx = df.query('diff < 0 and diff_prev > 0').index

  # assign signal values
  df[result_col] = none_signal
  df.loc[pos_idx, result_col] = pos_signal
  df.loc[neg_idx, result_col] = neg_signal
  
  return df[[result_col]]

# calculate signal that generated from trigering boundaries
def cal_boundary_signal(df, upper_col, lower_col, upper_boundary, lower_boundary, result_col='signal', pos_signal='b', neg_signal='s', none_signal='n'):
  """
  Calculate signal generated from triger of boundaries
  When upper_col breakthrough upper_boundary, positive signal will be generated
  When lower_col breakthrough lower_boundary, negative signal will be generated 

  :param df: original dffame which contains a fast line and a slow line
  :param upper_col: columnname of the positive column
  :param lower_col: columnname of the negative column
  :param upper_boundary: upper boundary
  :param lower_boundary: lower boundary
  :param result_col: columnname of the result
  :param pos_signal: the value of positive signal
  :param neg_siganl: the value of negative signal
  :param none_signal: the value of none signal
  :returns: series of the result column
  :raises: none
  """
  # copy dataframe
  df = df.copy()

  # calculate signals
  pos_idx = df.query('%(column)s > %(value)s' % dict(column=upper_col, value=upper_boundary)).index
  neg_idx = df.query('%(column)s < %(value)s' % dict(column=lower_col, value=lower_boundary)).index

  # assign signal values
  df[result_col] = none_signal
  df.loc[pos_idx, result_col] = pos_signal
  df.loc[neg_idx, result_col] = neg_signal

  return df[[result_col]]

# replace signal values 
def replace_signal(df, signal_col='signal', replacement={'b':1, 's':-1, 'n': 0}):
  """
  Replace signals with different values
  :param df: df that contains signal column
  :param signal_col: column name of the signal
  :param replacement: replacement, key is original value, value is the new value
  :returns: df with signal values replaced
  :raises: none
  """
  # copy dataframe
  new_df = df.copy()

  # find and replace
  for i in replacement.keys():
    new_df[signal_col].replace(to_replace=i, value=replacement[i], inplace=True)

  return new_df

# remove duplicated signals
def remove_redundant_signal(df, signal_col='signal', pos_signal='b', neg_signal='s', none_signal='n', keep='first'):
  """
  Remove redundant (duplicated continuous) signals, keep only the first or the last one

  :param df: signal dataframe
  :param signal_col: columnname of the signal value
  :param keep: which one to keep: first/last
  :param pos_signal: the value of positive signal
  :param neg_siganl: the value of negative signal
  :param none_signal: the value of none signal  
  :returns: signal dataframe with redundant signal removed
  :raises: none
  """
  # copy dataframe
  df = df.copy()
  
  # initialize
  signals = df.query('{signal} != "{none_signal}"'.format(signal=signal_col, none_signal=none_signal)).copy()
  movement = {'first': 1, 'last': -1}.get(keep)

  # find duplicated signals and set to none_signal
  if len(signals) > 0 and movement is not None:
    signals['is_dup'] = signals[signal_col] + signals[signal_col].shift(movement)
    dup_idx = signals.query('is_dup == "{p}{p}" or is_dup == "{n}{n}"'.format(p=pos_signal, n=neg_signal)).index

    if len(dup_idx) > 0:
      df.loc[dup_idx, signal_col] = none_signal

  return df



# ================================================ Self-defined TA ================================================== #
# linear regression
def linear_fit(df, target_col, periods):
  """
  Calculate slope for selected piece of data
  :param df: dataframe
  :param target_col: target column name
  :param periods: input data length 
  :returns: slope of selected data from linear regression
  :raises: none
  """

  if len(df) <= periods:
    return {'slope': 0, 'intecept': 0}
  
  else:
    x = range(1, periods+1)
    y = df[target_col].fillna(0).tail(periods).values.tolist()
    lr = linregress(x, y)

    return {'slope': lr[0], 'intecept': lr[1]}

# calculate peak / trough in price
def cal_peak_trough(df, target_col, height=None, threshold=None, distance=None, width=None, result_col='signal', peak_signal='p', trough_signal='t', none_signal='n'):
  """
  Calculate the position (signal) of the peak/trough of the target column

  :param df: original dataframe which contains target column
  :param result_col: columnname of the result
  :param peak_signal: the value of the peak signal
  :param trough_signal: the value of the trough signal
  :param none_signal: the value of the none signal
  :further_filter: if the peak/trough value is higher/lower than the average of its former and later peak/trough values, this peak/trough is valid
  :returns: series of peak/trough signal column
  :raises: none
  """
  # copy dataframe
  df = df.copy()
  
  try:
    # find peaks 
    peaks, _ = find_peaks(df[target_col], height=height, threshold=threshold, distance=distance, width=width)
    peaks = df.iloc[peaks,].index

    # find troughs
    troughs, _ = find_peaks(-df[target_col], height=height, threshold=threshold, distance=distance, width=width)
    troughs = df.iloc[troughs,].index

    # set signal values
    df[result_col] = none_signal
    df.loc[peaks, result_col] = peak_signal
    df.loc[troughs, result_col] = trough_signal
    
  except Exception as e:
    print(e, 'using self-defined method')
    
    further_filter=True

    # previous value of the target column
    previous_target_col = 'previous_' + target_col
    df[previous_target_col] = df[target_col].shift(1)

    # when value goes down, it means it is currently at peak
    peaks = df.query('%(t)s < %(pt)s' % dict(t=target_col, pt=previous_target_col)).index
    # when value goes up, it means it is currently at trough
    troughs = df.query('%(t)s > %(pt)s' % dict(t=target_col, pt=previous_target_col)).index
  
    # set signal values
    df[result_col] = none_signal
    df.loc[peaks, result_col] = peak_signal
    df.loc[troughs, result_col] = trough_signal
  
    # shift the signal back by 1 unit
    df[result_col] = df[result_col].shift(-1)
  
    # remove redundant signals
    df = remove_redundant_signal(df=df, signal_col=result_col, keep='first', pos_signal=peak_signal, neg_signal=trough_signal, none_signal=none_signal)
  
    # further filter the signals
    if further_filter:
      
      # get all peak/trough signals
      peak = df.query('%(r)s == "%(p)s"' % dict(r=result_col, p=peak_signal)).index.tolist()
      trough = df.query('%(r)s == "%(t)s"' % dict(r=result_col, t=trough_signal)).index.tolist()
        
      # peak/trough that not qualified
      false_peak = []
      false_trough = []
    
      # filter peak signals
      for i in range(len(peak)):
        current_idx = peak[i]
        benchmark = 0
      
        # the peak is not qualified if it is lower that the average of previous 2 troughs
        previous_troughs = df[:current_idx].query('%(r)s == "%(t)s"' % dict(r=result_col, t=trough_signal)).tail(2)
        if len(previous_troughs) > 0:
          benchmark = previous_troughs[target_col].mean()
        
        if df.loc[current_idx, target_col] < benchmark:
          false_peak.append(current_idx)
        
      # filter trough signals
      for i in range(len(trough)):        
        current_idx = trough[i]
        benchmark = 0

        # the trough is not qualified if it is lower that the average of previous 2 peaks
        previous_peaks = df[:current_idx].query('%(r)s == "%(p)s"' % dict(r=result_col, p=peak_signal)).tail(2)
        if len(previous_peaks) > 0:
          benchmark = previous_peaks[target_col].mean()
      
        if df.loc[current_idx, target_col] > benchmark:
          false_trough.append(current_idx)
          
      df.loc[false_peak, result_col] = none_signal
      df.loc[false_trough, result_col] = none_signal
      df.fillna('n')

  return df[[result_col]]

# calculate moving average 
def cal_moving_average(df, target_col, ma_windows=[50, 105], start=None, end=None, window_type='em'):
  """
  Calculate moving average of the tarhet column with specific window size

  :param df: original dataframe which contains target column
  :param ma_windows: a list of moving average window size to be calculated
  :param start: start date of the data
  :param end: end date of the data
  :param window_type: which moving window to be used: sm/em
  :returns: dataframe with moving averages
  :raises: none
  """
  # copy dataframe
  df = df[start:end].copy()

  # select moving window type
  if window_type == 'em':
    mw_func = em
  elif window_type == 'sm':
    mw_func = sm
  else:
    print('Unknown moving window type')
    return df

  # calculate moving averages
  for mw in ma_windows:
    ma_col = '%(target_col)s_ma_%(window_size)s' % dict(target_col=target_col, window_size=mw)
    df[ma_col] = mw_func(series=df[target_col], periods=mw).mean()
  
  return df

# add candle stick features 
def add_candlestick_features(df, close='Close', open='Open', high='High', low='Low', volume='Volume'):
  """
  Add candlestick dimentions for dataframe

  :param df: original OHLCV dataframe
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :returns: dataframe with candlestick columns
  :raises: none
  """
  # copy dataframe
  df = df.copy()
  
  # shadow
  df['shadow'] = (df[high] - df[low])    
  
  # entity
  df['entity'] = abs(df[close] - df[open])

  # upper/lower shadow
  df['upper_shadow'] = 0
  df['lower_shadow'] = 0
  df['candle_color'] = 0
  
  # up and down rows
  up_idx = df[open] < df[close]
  down_idx = df[open] >= df[close]
  
  # up
  df.loc[up_idx, 'candle_color'] = 1
  df.loc[up_idx, 'upper_shadow'] = (df.loc[up_idx, high] - df.loc[up_idx, close])
  df.loc[up_idx, 'lower_shadow'] = (df.loc[up_idx, open] - df.loc[up_idx, low])
  
  # down
  df.loc[down_idx, 'candle_color'] = -1
  df.loc[down_idx, 'upper_shadow'] = (df.loc[down_idx, high] - df.loc[down_idx, open])
  df.loc[down_idx, 'lower_shadow'] = (df.loc[down_idx, close] - df.loc[down_idx, low])
  
  return df



# ================================================ Trend indicators ================================================= #
# ADX(Average Directional Index) 
def add_adx_features(df, n=14, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True, adx_threshold=25):
  """
  Calculate ADX(Average Directional Index)

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param adx_threshold: the threshold to filter none-trending signals
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
  col_to_drop = []

  # calculate true range
  df = add_atr_features(df=df, n=n, cal_signal=False)

  # plus/minus directional movements
  df['high_diff'] = df[high] - df[high].shift(1)
  df['low_diff'] = df[low].shift(1) - df[low]
  df['zero'] = 0
  df['pdm'] = df['high_diff'].combine(df['zero'], lambda x1, x2: get_min_max(x1, x2, 'max'))
  df['mdm'] = df['low_diff'].combine(df['zero'], lambda x1, x2: get_min_max(x1, x2, 'max'))
  
  # plus/minus directional indicators
  df['pdi'] = 100 * em(series=df['pdm'], periods=n).mean() / df['atr']
  df['mdi'] = 100 * em(series=df['mdm'], periods=n).mean() / df['atr']

  # directional movement index
  df['dx'] = 100 * abs(df['pdi'] - df['mdi']) / (df['pdi'] + df['mdi'])

  # Average directional index
  df['adx'] = em(series=df['dx'], periods=n).mean()
  idx = df.index.tolist()
  for i in range(n*2, len(df)-1):
    current_idx = idx[i]
    previous_idx = idx[i-1]
    df.loc[current_idx, 'adx'] = (df.loc[previous_idx, 'adx'] * (n-1) + df.loc[current_idx, 'dx']) / n

  # adx trend
  df['adx_trend'] = (df['pdi'] - df['mdi']) * (df['adx']/adx_threshold)
  df['adx_trend'] = (df['adx_trend'] - df['adx_trend'].mean()) / df['adx_trend'].std()

  # fill na values
  if fillna:
    for col in ['pdm', 'mdm', 'atr', 'pdi', 'mdi', 'dx', 'adx']:
      df[col] = df[col].replace([np.inf, -np.inf], np.nan).fillna(0)

  # calculate signals
  if cal_signal:
    df['adx_signal'] = cal_crossover_signal(df=df, fast_line='adx_trend', slow_line='zero')

  df.drop(['high_diff', 'low_diff', 'zero', 'pdm', 'mdm', 'atr'], axis=1, inplace=True)

  return df

# Aroon
def add_aroon_features(df, n=25, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True, boundary=[50, 50]):
  """
  Calculate Aroon

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param boundary: upper and lower boundary for calculating signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate aroon up and down indicators
  aroon_up = df[close].rolling(n, min_periods=0).apply(lambda x: float(np.argmax(x) + 1) / n * 100, raw=True)
  aroon_down = df[close].rolling(n, min_periods=0).apply(lambda x: float(np.argmin(x) + 1) / n * 100, raw=True)
  
  # fill na value with 0
  if fillna:
    aroon_up = aroon_up.replace([np.inf, -np.inf], np.nan).fillna(0)
    aroon_down = aroon_down.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign values to df
  df['aroon_up'] = aroon_up
  df['aroon_down'] = aroon_down
  df['aroon_idx'] = (df['aroon_up']-50) + (50-df['aroon_down'])

  # calculate aroon signal
  if cal_signal:
    upper_boundary = max(boundary)
    lower_boundary = min(boundary)
    pos_idx = df.query('aroon_up > %(upper_boundary)s and aroon_down < %(lower_boundary)s' % dict(upper_boundary=upper_boundary, lower_boundary=lower_boundary)).index
    neg_idx = df.query('aroon_up < %(upper_boundary)s and aroon_down > %(lower_boundary)s' % dict(upper_boundary=upper_boundary, lower_boundary=lower_boundary)).index

    df['aroon_signal'] = 'n'
    df.loc[pos_idx, 'aroon_signal'] = 'b'
    df.loc[neg_idx, 'aroon_signal'] = 's'

  return df

# CCI(Commidity Channel Indicator)
def add_cci_features(df, n=20, c=0.015, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True, boundary=[200, -200]):
  """
  Calculate CCI(Commidity Channel Indicator) 

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param c: constant value used in cci calculation
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param boundary: upper and lower boundary for calculating signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate cci
  pp = (df[high] + df[low] + df[close]) / 3.0
  mad = lambda x : np.mean(np.abs(x-np.mean(x)))
  cci = (pp - pp.rolling(n, min_periods=0).mean()) / (c * pp.rolling(n).apply(mad,True))

  # assign values to dataframe
  df['cci'] = cci

  # calculate siganl
  if cal_signal:
    upper_boundary = max(boundary)
    lower_boundary = min(boundary)
    df['cci_signal'] = cal_boundary_signal(df=df, upper_col='cci', lower_col='cci', upper_boundary=upper_boundary, lower_boundary=lower_boundary)

  return df

# DPO(Detrended Price Oscillator)
def add_dpo_features(df, n=20, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate DPO(Detrended Price Oscillator) 

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate dpo
  dpo = df[close].shift(int((0.5 * n) + 1)) - df[close].rolling(n, min_periods=0).mean()
  if fillna:
    dpo = dpo.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign values to df
  df['dpo'] = dpo

  # calculate_signal
  if cal_signal:
    df['zero'] = 0
    df['dpo_signal'] = cal_crossover_signal(df=df, fast_line='dpo', slow_line='zero')
    df.drop(labels='zero', axis=1, inplace=True)

  return df

# Ichimoku 
def add_ichimoku_features(df, n_short=9, n_medium=26, n_long=52, method='ta', is_shift=True, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_status=True, cal_signal=True):
  """
  Calculate Ichimoku indicators

  :param df: original OHLCV dataframe
  :param n_short: short window size
  :param n_medium: medium window size
  :param n_long: long window size
  :param method: original/ta way to calculate ichimoku indicators
  :param is_shift: whether to shift senkou_a and senkou_b n_medium units
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
  col_to_drop = []

  # use original method to calculate ichimoku indicators
  if method == 'original':
    df = cal_moving_average(df=df, target_col=high, ma_windows=[n_short, n_medium, n_long], window_type='sm')
    df = cal_moving_average(df=df, target_col=low, ma_windows=[n_short, n_medium, n_long], window_type='sm')

    # generate column names
    short_high = '%(col)s_ma_%(p)s' % dict(col=high, p=n_short)
    short_low = '%(col)s_ma_%(p)s' % dict(col=low, p=n_short)
    medium_high = '%(col)s_ma_%(p)s' % dict(col=high, p=n_medium)
    medium_low = '%(col)s_ma_%(p)s' % dict(col=low, p=n_medium)
    long_high = '%(col)s_ma_%(p)s' % dict(col=high, p=n_long)
    long_low = '%(col)s_ma_%(p)s' % dict(col=low, p=n_long)
    col_to_drop += [short_high, medium_high, long_high, short_low, medium_low, long_low]

    # calculate ichimoku indicators
    df['tankan'] = (df[short_high] + df[short_low]) / 2
    df['kijun'] = (df[medium_high] + df[medium_low]) / 2
    df['senkou_a'] = (df['tankan'] + df['kijun']) / 2
    df['senkou_b'] = (df[long_high] + df[long_low]) / 2
    df['chikan'] = df[close].shift(-n_medium)
  
  # use ta method to calculate ichimoku indicators
  elif method == 'ta':
    df['tankan'] = (df[high].rolling(n_short, min_periods=0).max() + df[low].rolling(n_short, min_periods=0).min()) / 2
    df['kijun'] = (df[high].rolling(n_medium, min_periods=0).max() + df[low].rolling(n_medium, min_periods=0).min()) / 2
    df['senkou_a'] = (df['tankan'] + df['kijun']) / 2
    df['senkou_b'] = (df[high].rolling(n_long, min_periods=0).max() + df[low].rolling(n_long, min_periods=0).min()) / 2
    df['chikan'] = df[close].shift(-n_medium)

  # shift senkou_a and senkou_b n_medium units
  if is_shift:
    df['senkou_a'] = df['senkou_a'].shift(n_medium)
    df['senkou_b'] = df['senkou_b'].shift(n_medium)

  
  if cal_status:
    
    # ================================ Cloud status ===================================
    # cloud color change, cloud height (how thick is the cloud)
    df['cloud_shift'] = cal_crossover_signal(df=df, fast_line='senkou_a', slow_line='senkou_b', pos_signal=1, neg_signal=-1, none_signal=0)
    df['cloud_height'] = round((df['senkou_a'] - df['senkou_b'])/df[close], ndigits=3)
    green_idx = df.query('cloud_height > 0').index
    red_idx = df.query('cloud_height <= 0').index

    # cloud width (how has it last)
    df['cloud_width'] = 0
    df.loc[green_idx, 'cloud_width'] = 1
    df.loc[red_idx, 'cloud_width'] = -1

    # cloud top and bottom
    df['cloud_top'] = 0
    df.loc[green_idx, 'cloud_top'] = df['senkou_a']
    df.loc[red_idx, 'cloud_top'] = df['senkou_b']
    df['cloud_bottom'] = 0
    df.loc[green_idx, 'cloud_bottom'] = df['senkou_b']
    df.loc[red_idx, 'cloud_bottom'] = df['senkou_a']

    # calculate how long current cloud has lasted
    idx = df.index.tolist()
    for i in range(1, len(df)):
      current_idx = idx[i]
      previous_idx = idx[i-1]
      current_cloud_period = df.loc[current_idx, 'cloud_width']
      previous_cloud_period = df.loc[previous_idx, 'cloud_width']

      # calculate how long the cloud has last
      if current_cloud_period * previous_cloud_period > 0:
        df.loc[current_idx, 'cloud_width'] += previous_cloud_period

    # ================================ Close breakthrough =============================
    # calculate distance between Close and each ichimoku lines    
    line_weight = {'kijun':1, 'tankan':1, 'cloud_top':1, 'cloud_bottom':1}
    line_name = {"kijun":"基准", "tankan":"转换", "cloud_top":"云顶", "cloud_bottom":"云底"} 
    df['break_up'] = ''
    df['break_down'] = ''
    df['breakthrough'] = 0
    col_to_drop.append('breakthrough')

    for line in line_weight.keys():
      # set weight for this line
      weight = line_weight[line]

      # calculate breakthrough
      line_signal_name = 'signal_%s' % line
      df[line_signal_name] = cal_crossover_signal(df=df, fast_line=close, slow_line=line, pos_signal=weight, neg_signal=-weight, none_signal=0)
      
      # record breakthrough
      up_idx = df.query('%(name)s == %(value)s' % dict(name=line_signal_name, value=weight)).index
      down_idx = df.query('%(name)s == %(value)s' % dict(name=line_signal_name, value=-weight)).index      
      df.loc[up_idx, 'break_up'] = df.loc[up_idx, 'break_up'] + line_name[line] + ','
      df.loc[down_idx, 'break_down'] = df.loc[down_idx, 'break_down'] + line_name[line] + ','
      
      # accumulate breakthrough signals
      df['breakthrough'] = df['breakthrough'].astype(int) +df[line_signal_name].astype(int)

      # calculate distance between close price and indicator
      df['close_to_' + line] = round((df[close] - df[line]) / df[close], ndigits=3)

      # drop line signal columns
      col_to_drop.append(line_signal_name)

    # ================================ Signal =========================================
    if cal_signal:

      # calculate Close position corresponding to kijun and tankan
      # calculate position of Close, corresponding to kama_fast and kama_slow
      df['ichimoku_position'] = ''
      fast = 'tankan'
      slow = 'kijun'
      high_idx = df.query('{close} > {fast} > {slow}'.format(close=close, fast=fast, slow=slow)).index
      mid_high_idx = df.query('{fast} > {close} > {slow}'.format(close=close, fast=fast, slow=slow)).index
      mid_low_idx = df.query('{slow} > {close} > {fast}'.format(close=close, fast=fast, slow=slow)).index
      low_idx = df.query('{slow} > {fast} > {close}'.format(close=close, fast=fast, slow=slow)).index
      df.loc[high_idx, 'ichimoku_position'] = 'h'
      df.loc[mid_high_idx, 'ichimoku_position'] = 'mh'
      df.loc[mid_low_idx, 'ichimoku_position'] = 'ml'
      df.loc[low_idx, 'ichimoku_position'] = 'l'

      # final signal
      df['ichimoku_signal'] =  df['signal_tankan']
      df = replace_signal(df=df, signal_col='ichimoku_signal', replacement={line_weight['tankan']: 'b', -line_weight['tankan']: 's', 0: 'n'})

    # drop redundant columns  
    df.drop(col_to_drop, axis=1, inplace=True)

  return df

# KST(Know Sure Thing)
def add_kst_features(df, r1=10, r2=15, r3=20, r4=30, n1=10, n2=10, n3=10, n4=15, nsign=9, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True, signal_mode='default'):
  """
  Calculate KST(Know Sure Thing)

  :param df: original OHLCV dataframe
  :param r_1: r1 window size
  :param r_2: r2 window size
  :param r_3: r3 window size
  :param r_4: r4 window size
  :param n_1: n1 window size
  :param n_2: n2 window size
  :param n_3: n3 window size
  :param n_4: n4 window size
  :param n_sign: kst signal window size
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
  col_to_drop = []

  # calculate kst
  rocma1 = ((df[close] - df[close].shift(r1)) / df[close].shift(r1)).rolling(n1, min_periods=0).mean()
  rocma2 = ((df[close] - df[close].shift(r2)) / df[close].shift(r2)).rolling(n2, min_periods=0).mean()
  rocma3 = ((df[close] - df[close].shift(r3)) / df[close].shift(r3)).rolling(n3, min_periods=0).mean()
  rocma4 = ((df[close] - df[close].shift(r4)) / df[close].shift(r4)).rolling(n4, min_periods=0).mean()
  
  kst = 100 * (rocma1 + 2 * rocma2 + 3 * rocma3 + 4 * rocma4)
  kst_sign = kst.rolling(nsign, min_periods=0).mean()

  # fill na value
  if fillna:
    kst = kst.replace([np.inf, -np.inf], np.nan).fillna(0)
    kst_sign = kst_sign.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign values to df
  df['kst'] = kst
  df['kst_sign'] = kst_sign
  df['kst_diff'] = df['kst'] - df['kst_sign']
  df['kst_diff'] = (df['kst_diff'] - df['kst_diff'].mean()) / df['kst_diff'].std()

  # calculate signal
  if cal_signal:
    df['zero'] = 0
    col_to_drop.append('zero')
    df['kst_signal'] = cal_crossover_signal(df=df, fast_line='kst_diff', slow_line='zero')

  df.drop('zero', axis=1, inplace=True)
  return df

# MACD(Moving Average Convergence Divergence)
def add_macd_features(df, n_fast=12, n_slow=26, n_sign=9, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate MACD(Moving Average Convergence Divergence)

  :param df: original OHLCV dataframe
  :param n_fast: ma window of fast ma
  :param n_slow: ma window of slow ma
  :paran n_sign: ma window of macd signal line
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate fast and slow ema of close price
  emafast = em(series=df[close], periods=n_fast, fillna=fillna).mean()
  emaslow = em(series=df[close], periods=n_slow, fillna=fillna).mean()
  
  # calculate macd, ema(macd), macd-ema(macd)
  macd = emafast - emaslow
  macd_sign = em(series=macd, periods=n_sign, fillna=fillna).mean()
  macd_diff = macd - macd_sign

  # fill na value with 0
  if fillna:
      macd = macd.replace([np.inf, -np.inf], np.nan).fillna(0)
      macd_sign = macd_sign.replace([np.inf, -np.inf], np.nan).fillna(0)
      macd_diff = macd_diff.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign valuse to df
  df['macd'] = macd
  df['macd_sign'] = macd_sign
  df['macd_diff'] = macd_diff

  # calculate crossover signal
  if cal_signal:
    df['zero'] = 0
    df['macd_signal'] = cal_crossover_signal(df=df, fast_line='macd_diff', slow_line='zero')
    df.drop(labels='zero', axis=1, inplace=True)

  return df

# Mass Index
def add_mi_features(df, n=9, n2=25, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Mass Index

  :param df: original OHLCV dataframe
  :param n: ema window of high-low difference
  :param n_2: window of cumsum of ema ratio
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  amplitude = df[high] - df[low]
  ema1 = em(series=amplitude, periods=n, fillna=fillna).mean()
  ema2 = em(series=ema1, periods=n, fillna=fillna).mean()
  mass = ema1 / ema2
  mass = mass.rolling(n2, min_periods=0).sum()
  
  # fillna value  
  if fillna:
    mass = mass.replace([np.inf, -np.inf], np.nan).fillna(n2)

  # assign value to df
  df['mi'] = mass

  # calculate signal
  if cal_signal:
    df['benchmark'] = 27
    df['triger_signal'] = cal_crossover_signal(df=df, fast_line='mi', slow_line='benchmark', pos_signal='b', neg_signal='n', none_signal='n')
    df['benchmark'] = 26.5
    df['complete_signal'] = cal_crossover_signal(df=df, fast_line='mi', slow_line='benchmark', pos_signal='n', neg_signal='s', none_signal='n')

    up_idx = df.query('triger_signal == "b"').index
    down_idx = df.query('complete_signal == "s"').index
    df['mi_signal'] = 'n'
    df.loc[up_idx, 'mi_signal'] = 'b'
    df.loc[down_idx, 'mi_signal'] = 's'

    df.drop(['benchmark', 'triger_signal', 'complete_signal'], axis=1, inplace=True)

  return df

# TRIX
def add_trix_features(df, n=15, n_sign=9, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True, signal_mode='mix'):
  """
  Calculate TRIX

  :param df: original OHLCV dataframe
  :param n: ema window of close price
  :param n_sign: ema window of signal line (ema of trix)
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate trix
  ema1 = em(series=df[close], periods=n, fillna=fillna).mean()
  ema2 = em(series=ema1, periods=n, fillna=fillna).mean()
  ema3 = em(series=ema2, periods=n, fillna=fillna).mean()
  trix = (ema3 - ema3.shift(1)) / ema3.shift(1)
  trix *= 100

  # fillna value
  if fillna:
    trix = trix.replace([np.inf, -np.inf], np.nan).fillna(0)
  
  # assign value to df
  df['trix'] = trix
  df['trix_sign'] = em(series=trix, periods=n_sign, fillna=fillna).mean()

  # calculate signal
  if cal_signal:

    # zero line crossover
    df['zero'] = 0
    df['zero_crossover'] = cal_crossover_signal(df=df, fast_line='trix', slow_line='zero')

    # signal line crossover
    df['sign_crossover'] = cal_crossover_signal(df=df, fast_line='trix', slow_line='trix_sign')
    
    if signal_mode == 'zero':
      df['trix_signal'] = df['zero_crossover']

    elif signal_mode == 'sign':
      df['trix_signal'] = df['sign_crossover']

    elif signal_mode == 'mix':
      up_idx = df.query('sign_crossover  == "b"').index
      down_idx = df.query('zero_crossover == "s"').index

      df['trix_signal'] = 'n'
      df.loc[up_idx, 'trix_signal'] = 'b'
      df.loc[down_idx, 'trix_signal'] = 's'

    else:
      df['trix_signal'] = 'n'

    df.drop(['zero', 'zero_crossover', 'sign_crossover'], axis=1, inplace=True)

  return df

# Vortex
def add_vortex_features(df, n=14, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Vortex indicator

  :param df: original OHLCV dataframe
  :param n: ema window of close price
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate vortex
  tr = (df[high].combine(df[close].shift(1), max) - df[low].combine(df[close].shift(1), min))
  trn = tr.rolling(n).sum()

  vmp = np.abs(df[high] - df[low].shift(1))
  vmm = np.abs(df[low] - df[high].shift(1))

  vip = vmp.rolling(n, min_periods=0).sum() / trn
  vin = vmm.rolling(n, min_periods=0).sum() / trn

  if fillna:
    vip = vip.replace([np.inf, -np.inf], np.nan).fillna(1)
    vin = vin.replace([np.inf, -np.inf], np.nan).fillna(1)
  
  # assign values to df
  df['vortex_pos'] = vip
  df['vortex_neg'] = vin

  # calculate signal
  if cal_signal:
    df['vortex_signal'] = cal_crossover_signal(df=df, fast_line='vortex_pos', slow_line='vortex_neg')

  return df



# ================================================ Volume indicators ================================================ #
# Accumulation Distribution Index
def add_adi_features(df, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Accumulation Distribution Index

  :param df: original OHLCV dataframe
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """

  # copy dataframe
  df = df.copy()

  # calculate ADI
  clv = ((df[close] - df[low]) - (df[high] - df[close])) / (df[high] - df[low])
  clv = clv.fillna(0.0)  # float division by zero
  ad = clv * df[volume]
  ad = ad + ad.shift(1)

  # fill na values
  if fillna:
    ad = ad.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign adi to df
  df['adi'] = ad

  # calculate signals
  if cal_signal:
    df['adi_signal'] = 'n'

  return df

# *Chaikin Money Flow (CMF)
def add_cmf_features(df, n=20, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Chaikin Money FLow

  :param df: original OHLCV dataframe
  :param n: ema window of close price
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """

  # copy dataframe
  df = df.copy()

  # calculate cmf
  mfv = ((df[close] - df[low]) - (df[high] - df[close])) / (df[high] - df[low])
  mfv = mfv.fillna(0.0)  # float division by zero
  mfv *= df[volume]
  cmf = (mfv.rolling(n, min_periods=0).sum() / df[volume].rolling(n, min_periods=0).sum())

  # fill na values
  if fillna:
    cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign cmf to df
  df['cmf'] = cmf

  # calculate signals
  if cal_signal:
    df['cmf_signal'] = cal_boundary_signal(df=df, upper_col='cmf', lower_col='cmf', upper_boundary=0.05, lower_boundary=-0.05, result_col='signal', pos_signal='b', neg_signal='s', none_signal='n')

  return df

# Ease of movement (EoM, EMV)
def add_eom_features(df, n=20, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Vortex indicator

  :param df: original OHLCV dataframe
  :param n: ema window of close price
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """

  # copy dataframe
  df = df.copy()
  col_to_drop = []

  # calculate eom
  eom = (df[high].diff(periods=1) + df[low].diff(periods=1)) * (df[high] - df[low]) / (df[volume] * 2)
  eom = eom.rolling(window=n, min_periods=0).mean()

  # fill na values
  if fillna:
    eom = eom.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign eom to df
  df['eom'] = eom
  
  # calculate eom_ma_14 and eom - eom_ma_14
  df = cal_moving_average(df=df, target_col='eom', ma_windows=[14], window_type='sm')
  df['eom_diff'] = df['eom'] - df['eom_ma_14']
  df['eom_diff'] = (df['eom_diff'] - df['eom_diff'].mean()) / df['eom_diff'].std()


  # calculate signals
  if cal_signal:
    df['zero'] = 0
    col_to_drop.append('zero')
    df['eom_signal'] = cal_crossover_signal(df=df, fast_line='eom_diff', slow_line='zero')

  df.drop('zero', axis=1, inplace=True)
  return df

# Force Index (FI)
def add_fi_features(df, n1=2, n2=22, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Force Index

  :param df: original OHLCV dataframe
  :param n: ema window of close price
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """

  # copy dataframe
  df = df.copy()

  # calculate fi
  fi = df[close].diff(n1) * df[volume]#.diff(n)
  fi_ema = em(series=fi, periods=n2).mean()

  # fill na values
  if fillna:
    fi = fi.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign fi to df
  df['fi'] = fi
  df['fi_ema'] = fi_ema

  # calculate signals
  if cal_signal:
    df['fi_signal'] = 'n'

  return df

# *Negative Volume Index (NVI)
def add_nvi_features(df, n=255, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Negative Volume Index (NVI)

  :param df: original OHLCV dataframe
  :param n: ema window of close price
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate nvi
  price_change = df[close].pct_change()*100
  vol_decress = (df[volume].shift(1) > df[volume])

  nvi = pd.Series(data=np.nan, index=df[close].index, dtype='float64', name='nvi')

  nvi.iloc[0] = 1000
  for i in range(1, len(nvi)):
    if vol_decress.iloc[i]:
      nvi.iloc[i] = nvi.iloc[i-1] + (price_change.iloc[i])
    else:
      nvi.iloc[i] = nvi.iloc[i-1]

  # fill na values
  if fillna:
    nvi = nvi.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign nvi to df
  df['nvi'] = nvi
  df['nvi_ema'] = em(series=nvi, periods=n).mean()

  # calculate signal
  if cal_signal:
    df['nvi_signal'] = 'n'

  return df

# *On-balance volume (OBV)
def add_obv_features(df, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Force Index

  :param df: original OHLCV dataframe
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate obv
  df['OBV'] = np.nan
  c1 = df[close] < df[close].shift(1)
  c2 = df[close] > df[close].shift(1)
  if c1.any():
    df.loc[c1, 'OBV'] = - df[volume]
  if c2.any():
    df.loc[c2, 'OBV'] = df[volume]
  obv = df['OBV'].cumsum()
  obv = obv.fillna(method='ffill')

  # fill na values
  if fillna:
    obv = obv.replace([np.inf, -np.inf], np.nan).fillna(0)


  # assign obv to df
  df['obv'] = obv

  # calculate signals
  if cal_signal:
    df['obv_signal'] = 'n'

  df.drop('OBV', axis=1, inplace=True)
  return df

# *Volume-price trend (VPT)
def add_vpt_features(df, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Vortex indicator

  :param df: original OHLCV dataframe
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate vpt
  df['close_change_rate'] = df[close].pct_change(periods=1)
  vpt = df[volume] * df['close_change_rate']
  vpt = vpt.shift(1) + vpt

  # fillna values
  if fillna:
    vpt = vpt.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign vpt value to df
  df['vpt'] = vpt

  # calculate signals
  if cal_signal:
    df['vpt_signal'] = 'n'

  # drop redundant columns
  df.drop(['close_change_rate'], axis=1, inplace=True)

  return df



# ================================================ Momentum indicators ============================================== #
# Awesome Oscillator
def add_ao_features(df, n_short=5, n_long=34, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Awesome Oscillator

  :param df: original OHLCV dataframe
  :param n_short: short window size for calculating sma
  :param n_long: long window size for calculating sma
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate ao
  mp = 0.5 * (df[high] + df[low])
  ao = mp.rolling(n_short, min_periods=0).mean() - mp.rolling(n_long, min_periods=0).mean()

  # fill na values
  if fillna:
    ao = ao.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign ao to df
  df['ao'] = ao

  # calculate signal
  if cal_signal:

    # zero line crossover
    df['zero'] = 0
    df['ao_signal'] = cal_crossover_signal(df=df, fast_line='ao', slow_line='zero')
    df.drop(['zero'], axis=1, inplace=True)

  return df

# Kaufman's Adaptive Moving Average (KAMA)
def cal_kama(df, n1=10, n2=2, n3=30, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False):
  """
  Calculate Kaufman's Adaptive Moving Average

  :param df: original OHLCV dataframe
  :param n1: number of periods for Efficiency Ratio(ER)
  :param n2: number of periods for the fastest EMA constant
  :param n3: number of periods for the slowest EMA constant
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate kama
  close_values = df[close].values
  vol = pd.Series(abs(df[close] - np.roll(df[close], 1)))

  ER_num = abs(close_values - np.roll(close_values, n1))
  ER_den = vol.rolling(n1).sum()
  ER = ER_num / ER_den

  sc = ((ER * (2.0/(n2+1.0) - 2.0/(n3+1.0)) + 2.0/(n3+1.0)) ** 2.0).values

  kama = np.zeros(sc.size)
  N = len(kama)
  first_value = True

  for i in range(N):
    if np.isnan(sc[i]):
      kama[i] = np.nan
    else:
      if first_value:
        kama[i] = close_values[i]
        first_value = False
      else:
        kama[i] = kama[i-1] + sc[i] * (close_values[i] - kama[i-1])

  kama = pd.Series(kama, name='kama', index=df[close].index)

  # fill na values
  if fillna:
    kama = kama.replace([np.inf, -np.inf], np.nan).fillna(df[close])

  # assign kama to df
  df['kama'] = kama

  return df

# Kaufman's Adaptive Moving Average (KAMA)
def add_kama_features(df, n_param={'kama_fast': [10, 2, 30], 'kama_slow': [10, 5, 30]}, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True, sensitive_mode=True):
  """
  Calculate Kaufman's Adaptive Moving Average Signal

  :param df: original OHLCV dataframe
  :param n_param: series of n parameters fro calculating kama in different periods
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate fast and slow kama
  for k in n_param.keys():
    tmp_n = n_param[k]
    if len(tmp_n) != 3:
      print(k, ' please provide all 3 parameters')
      continue
    else:
      n1 = tmp_n[0]
      n2 = tmp_n[1]
      n3 = tmp_n[2]
      df = cal_kama(df=df, n1=n1, n2=n2, n3=n3, close=close, open=open, high=high, low=low, volume=volume, fillna=fillna)
      df.rename(columns={'kama': k}, inplace=True)

  # calculate distance between close price and indicator
  kama_lines = ['kama_fast', 'kama_slow'] 
  for line in kama_lines:
    df['close_to_{line}'.format(line=line)] = round((df[close] - df[line]) / df[close], ndigits=3)

  # calculate kama signals  
  if cal_signal:
    if set(['kama_fast', 'kama_slow']) < set(df.columns):
      # add signals generated by close, kama_fast, kama_slow
      df['kama_close_fast_signal'] = cal_crossover_signal(df=df, fast_line=close, slow_line='kama_fast', result_col='kama_close_fast_signal', pos_signal='b', neg_signal='s', none_signal='n')
      df['kama_fast_slow_signal'] = cal_crossover_signal(df=df, fast_line='kama_fast', slow_line='kama_slow', result_col='kama_fast_slow_signal', pos_signal='b', neg_signal='s', none_signal='n')
      buy_idx = df.query('kama_close_fast_signal=="b" or kama_fast_slow_signal=="b"').index
      sell_idx = df.query('kama_close_fast_signal=="s" or kama_fast_slow_signal=="s"').index
      df['kama_signal'] = 'n'   
      df.loc[buy_idx, 'kama_signal'] = 'b'
      df.loc[sell_idx, 'kama_signal'] = 's'

      # calculate position of Close, corresponding to kama_fast and kama_slow
      df['kama_position'] = ''
      fast = 'kama_fast'
      slow = 'kama_slow'
      high_idx = df.query('{close} > {fast} > {slow}'.format(close=close, fast=fast, slow=slow)).index
      mid_high_idx = df.query('{fast} > {close} > {slow}'.format(close=close, fast=fast, slow=slow)).index
      mid_low_idx = df.query('{slow} > {close} > {fast}'.format(close=close, fast=fast, slow=slow)).index
      low_idx = df.query('{slow} > {fast} > {close}'.format(close=close, fast=fast, slow=slow)).index
      
      df.loc[high_idx, 'kama_position'] = 'h'
      df.loc[mid_high_idx, 'kama_position'] = 'mh'
      df.loc[mid_low_idx, 'kama_position'] = 'ml'
      df.loc[low_idx, 'kama_position'] = 'l'
      
    else:
      df['kama_signal'] = 'n'
      df['kama_position'] = 'n'
      print('please specify kama_fast and kama_slow parameters in n_param')

  return df

# Money Flow Index(MFI)
def add_mfi_features(df, n=14, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True, boundary=[20, 80]):
  """
  Calculate Money Flow Index Signal

  :param df: original OHLCV dataframe
  :param n: ma window size
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param boundary: boundaries for overbuy/oversell
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate adi
  typical_price = (df[high] + df[low] + df[close])  / 3.0

  df['up_or_down'] = 0
  df.loc[(typical_price > typical_price.shift(1)), 'up_or_down'] = 1
  df.loc[(typical_price < typical_price.shift(1)), 'up_or_down'] = -1

  money_flow = typical_price * df[volume] * df['up_or_down']

  n_positive_mf = money_flow.rolling(n).apply(
    lambda x: np.sum(np.where(x >= 0.0, x, 0.0)), 
    raw=True)

  n_negative_mf = abs(money_flow.rolling(n).apply(
    lambda x: np.sum(np.where(x < 0.0, x, 0.0)),
    raw=True))

  mfi = n_positive_mf / n_negative_mf
  mfi = (100 - (100 / (1 + mfi)))

  # fill na values, as 50 is the central line (mfi wave between 0-100)
  if fillna:
    mfi = mfi.replace([np.inf, -np.inf], np.nan).fillna(50)

  # assign mfi to df
  df['mfi'] = mfi

  # calculate signals
  if cal_signal:
    df['mfi_signal'] = cal_boundary_signal(df=df, upper_col='mfi', lower_col='mfi', upper_boundary=max(boundary), lower_boundary=min(boundary), result_col='signal', pos_signal='s', neg_signal='b', none_signal='n')
    df = remove_redundant_signal(df=df, signal_col='mfi_signal', pos_signal='s', neg_signal='b', none_signal='n', keep='first')

  df.drop('up_or_down', axis=1, inplace=True)
  return df

# Relative Strength Index (RSI)
def add_rsi_features(df, n=14, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True, boundary=[30, 70]):
  """
  Calculate Relative Strength Index

  :param df: original OHLCV dataframe
  :param n: ma window size
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param boundary: boundaries for overbuy/oversell
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate RSI
  diff = df[close].pct_change(1)
  
  up = diff.copy()
  up[diff < 0] = 0
  
  down = -diff.copy()
  down[diff > 0] = 0
  
  emaup = up.ewm(com=n-1, min_periods=0).mean()
  emadown = down.ewm(com=n-1, min_periods=0).mean()

  rsi = 100 * emaup / (emaup + emadown)

  # fill na values, as 50 is the central line (rsi wave between 0-100)
  if fillna:
    rsi = rsi.replace([np.inf, -np.inf], np.nan).fillna(50)

  # assign rsi to df
  df['rsi'] = rsi

  # calculate signals
  if cal_signal:
    df['rsi_signal'] = cal_boundary_signal(df=df, upper_col='rsi', lower_col='rsi', upper_boundary=max(boundary), lower_boundary=min(boundary), result_col='signal', pos_signal='s', neg_signal='b', none_signal='n')
    df = remove_redundant_signal(df=df, signal_col='rsi_signal', pos_signal='s', neg_signal='b', none_signal='n', keep='first')

  return df

# Stochastic Oscillator
def add_stoch_features(df, n=14, d_n=3, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True, boundary=[20, 80]):
  """
  Calculate Stochastic Oscillator

  :param df: original OHLCV dataframe
  :param n: ma window size
  :param d_n: ma window size for stoch
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param boundary: boundaries for overbuy/oversell
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate stochastic
  stoch_min = df[low].rolling(n, min_periods=0).min()
  stoch_max = df[high].rolling(n, min_periods=0).max()
  stoch_k = 100 * (df[close] - stoch_min) / (stoch_max - stoch_min)
  stoch_d = stoch_k.rolling(d_n, min_periods=0).mean()

  # fill na values, as 50 is the central line (rsi wave between 0-100)
  if fillna:
    stoch_k = stoch_k.replace([np.inf, -np.inf], np.nan).fillna(50)
    stoch_d = stoch_d.replace([np.inf, -np.inf], np.nan).fillna(50)

  # assign stochastic values to df
  df['stoch_k'] = stoch_k
  df['stoch_d'] = stoch_d

  # calculate signals
  if cal_signal:
    df['stoch_k_d_signal'] = cal_crossover_signal(df=df, fast_line='stoch_k', slow_line='stoch_d', result_col='signal', pos_signal='b', neg_signal='s', none_signal='n')
    df['stoch_boundary_signal'] = cal_boundary_signal(df=df, upper_col='stoch_k', lower_col='stoch_k', upper_boundary=max(boundary), lower_boundary=min(boundary), result_col='signal', pos_signal='s', neg_signal='b', none_signal='n')
    # df = remove_redundant_signal(df=df, signal_col='stoch_boundary_signal', pos_signal='s', neg_signal='b', none_signal='n', keep='first')

  return df

# True strength index (TSI)
def add_tsi_features(df, r=25, s=13, ema_period=7, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate True strength index

  :param df: original OHLCV dataframe
  :param r: ma window size for high
  :param s: ma window size for low
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate tsi
  m = df[close] - df[close].shift(1, fill_value=df[close].mean())
  m1 = m.ewm(r).mean().ewm(s).mean()
  m2 = abs(m).ewm(r).mean().ewm(s).mean()
  tsi = 100 * (m1 / m2)
  tsi_sig = em(series=tsi, periods=ema_period).mean()

  # fill na values
  if fillna:
    tsi = tsi.replace([np.inf, -np.inf], np.nan).fillna(0)
    tsi_sig = tsi_sig.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign tsi to df
  df['tsi'] = tsi
  df['tsi_sig'] = tsi_sig

  # calculate signal
  if cal_signal:
    df['zero'] = 0
    df['tsi_fast_slow_signal'] = cal_crossover_signal(df=df, fast_line='tsi', slow_line='tsi_sig', result_col='signal', pos_signal='b', neg_signal='s', none_signal='n')
    df['tsi_centerline_signal'] = cal_crossover_signal(df=df, fast_line='tsi', slow_line='zero', result_col='signal', pos_signal='b', neg_signal='s', none_signal='n')

  return df

# Ultimate Oscillator
def add_uo_features(df, s=7, m=14, l=28, ws=4.0, wm=2.0, wl=1.0, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=False):
  """
  Calculate Ultimate Oscillator

  :param df: original OHLCV dataframe
  :param s: short ma window size 
  :param m: mediem window size
  :param l: long window size
  :param ws: weight for short period
  :param wm: weight for medium period
  :param wl: weight for long period
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate uo
  min_l_or_pc = df[close].shift(1, fill_value=df[close].mean()).combine(df[low], min)
  max_h_or_pc = df[close].shift(1, fill_value=df[close].mean()).combine(df[high], max)

  bp = df[close] - min_l_or_pc
  tr = max_h_or_pc - min_l_or_pc

  avg_s = bp.rolling(s, min_periods=0).sum() / tr.rolling(s, min_periods=0).sum()
  avg_m = bp.rolling(m, min_periods=0).sum() / tr.rolling(m, min_periods=0).sum()
  avg_l = bp.rolling(l, min_periods=0).sum() / tr.rolling(l, min_periods=0).sum()

  uo = 100.0 * ((ws * avg_s) + (wm * avg_m) + (wl * avg_l)) / (ws + wm + wl)

  # fill na values
  if fillna:
    uo = uo.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign uo to df
  df['uo'] = uo

  # calculate signal
  if cal_signal:
    df['uo_signal'] = 'n'

  return df

# Williams %R
def add_wr_features(df, lbp=14, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True, boundary=[-20, -80]):
  """
  Calculate Williams %R

  :param df: original OHLCV dataframe
  :param lbp: look back period
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate wr
  hh = df[high].rolling(lbp, min_periods=0).max()
  ll = df[low].rolling(lbp, min_periods=0).min()

  wr = -100 * (hh - df[close]) / (hh - ll)

  # fill na values
  if fillna:
    wr = wr.replace([np.inf, -np.inf], np.nan).fillna(-50)

  # assign wr to df
  df['wr'] = wr

  # calulate signal
  if cal_signal:
    df['wr_signal'] = cal_boundary_signal(df=df, upper_col='wr', lower_col='wr', upper_boundary=max(boundary), lower_boundary=min(boundary), result_col='signal', pos_signal='s', neg_signal='b', none_signal='n')

  return df



# ================================================ Volatility indicators ============================================ #
# Average True Range
def add_atr_features(df, n=14, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Average True Range

  :param df: original OHLCV dataframe
  :param n: ema window
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate true range
  df['h_l'] = df[low] - df[low]
  df['h_pc'] = abs(df[high] - df[close].shift(1))
  df['l_pc'] = abs(df[low] - df[close].shift(1))
  df['tr'] = df[['h_l', 'h_pc', 'l_pc']].max(axis=1)

  # calculate average true range
  df['atr'] = sm(series=df['tr'], periods=n, fillna=True).mean()
  
  idx = df.index.tolist()
  for i in range(n, len(df)):
    current_idx = idx[i]
    previous_idx = idx[i-1]
    df.loc[current_idx, 'atr'] = (df.loc[previous_idx, 'atr'] * 13 + df.loc[current_idx, 'tr']) / 14

  # fill na value
  if fillna:
    df['atr'] = df['atr'].replace([np.inf, -np.inf], np.nan).fillna(0)

  # calculate signal
  if cal_signal:
    df['atr_signal'] = df['tr'] - df['atr']

  df.drop(['h_l', 'h_pc', 'l_pc'], axis=1, inplace=True)

  return df

# Mean Reversion
def add_mean_reversion_features(df, n=100, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True, mr_threshold=2):
  """
  Calculate Mean Reversion

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param mr_threshold: the threshold to triger signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate change rate of close price
  df = cal_change_rate(df=df, target_col=close, periods=1, add_accumulation=True)
  target_col = ['rate', 'acc_rate', 'acc_day']

  # calculate the (current value - moving avg) / moving std
  for col in target_col:
    mw = sm(series=df[col], periods=n)
    tmp_mean = mw.mean()
    tmp_std = mw.std()
    df[col+'_bias'] = (df[col] - tmp_mean) / (tmp_std)

  # calculate the expected change rate that will triger signal
  result = cal_mean_reversion_expected_rate(df=df, rate_col='acc_rate', n=n, mr_threshold=mr_threshold)
  last_acc_rate = df['acc_rate'].tail(1).values[0]
  last_close = df[close].tail(1).values[0]

  up = down = 0
  if last_acc_rate > 0:
    up = max(result) - last_acc_rate
    down = min(result)
  else:
    up = max(result)
    down = min(result) - last_acc_rate

  up_price = round((1+up) * last_close, ndigits=2)
  down_price = round((1+down) * last_close, ndigits=2)
  up = round(up * 100, ndigits=0) 
  down = round(down * 100, ndigits=0) 
  df['mr_price'] = '%(up_price)s(%(up)s%%), %(down_price)s(%(down)s%%)' % dict(up_price=up_price, up=up, down_price=down_price, down=down)

  # calculate mr signal
  if cal_signal:
    df['rate_signal'] = cal_boundary_signal(df=df, upper_col='rate_bias', lower_col='rate_bias', upper_boundary=mr_threshold, lower_boundary=-mr_threshold, pos_signal=1, neg_signal=-1, none_signal=0)
    df['acc_rate_signal'] = cal_boundary_signal(df=df, upper_col='acc_rate_bias', lower_col='acc_rate_bias', upper_boundary=mr_threshold, lower_boundary=-mr_threshold, pos_signal=1, neg_signal=-1, none_signal=0)
    df['mr_signal'] = df['rate_signal'].astype(int) + df['acc_rate_signal'].astype(int)
    df = replace_signal(df=df, signal_col='mr_signal', replacement={0: 'n', 1: 'n', -1:'n', 2:'b', -2:'s'})
    df.drop(['rate_signal', 'acc_rate_signal'], axis=1, inplace=True)   

  return df

# Price that will triger mean reversion signal
def cal_mean_reversion_expected_rate(df, rate_col, n=100, mr_threshold=2):
  """
  Calculate the expected rate change to triger mean-reversion signals

  :param df: original dataframe which contains rate column
  :param rate_col: columnname of the change rate values
  :param n: windowsize of the moving window
  :param mr_threshold: the multiple of moving std to triger signals
  :returns: the expected up/down rate to triger signals
  :raises: none
  """
  x = sympy.Symbol('x')

  df = np.hstack((df.tail(n-1)[rate_col].values, x))
  ma = df.mean()
  std = sympy.sqrt(sum((df - ma)**2)/(n-1))
  result = sympy.solve(((x - ma)**2) - ((mr_threshold*std)**2), x)

  return result

# Bollinger Band
def add_bb_features(df, n=20, ndev=2, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Bollinger Band

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param ndev: standard deviation factor
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate bollinger band 
  mavg = sm(series=df[close], periods=n).mean()
  mstd = sm(series=df[close], periods=n).std(ddof=0)
  high_band = mavg + ndev*mstd
  low_band = mavg - ndev*mstd

  # fill na values
  if fillna:
      mavg = mavg.replace([np.inf, -np.inf], np.nan).fillna(method='backfill')
      mstd = mstd.replace([np.inf, -np.inf], np.nan).fillna(method='backfill')
      high_band = high_band.replace([np.inf, -np.inf], np.nan).fillna(method='backfill')
      low_band = low_band.replace([np.inf, -np.inf], np.nan).fillna(method='backfill')
      
  # assign values to df
  df['mavg'] = mavg
  df['mstd'] = mstd
  df['bb_high_band'] = high_band
  df['bb_low_band'] = low_band

  if cal_signal:
    df['bb_signal'] = 'n'
    buy_idx = df.query('%(column)s < bb_low_band' % dict(column=close)).index
    sell_idx = df.query('%(column)s > bb_high_band' % dict(column=close)).index
    df.loc[buy_idx, 'bb_signal'] = 'b'
    df.loc[sell_idx, 'bb_signal'] = 's'

  return df

# Donchian Channel
def add_dc_features(df, n=20, close='Close', open='Open', high='High', low='Low', volume='Volume', fillna=False, cal_signal=True):
  """
  Calculate Donchian Channel

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate dochian channel
  high_band = df[close].rolling(n, min_periods=0).max()
  low_band = df[close].rolling(n, min_periods=0).min()
  middle_band = (high_band + low_band)/2

  # fill na values
  if fillna:
    high_band = high_band.replace([np.inf, -np.inf], np.nan).fillna(method='backfill')
    low_band = low_band.replace([np.inf, -np.inf], np.nan).fillna(method='backfill')
    middle_band = middle_band.replace([np.inf, -np.inf], np.nan).fillna(method='backfill')

  # assign values to df
  df['dc_high_band'] = high_band
  df['dc_low_band'] = low_band
  df['dc_middle_band'] = middle_band

  # calculate signals
  if cal_signal:
    df['dc_signal'] = 'n'
    buy_idx = df.query('%(column)s <= dc_low_band' % dict(column=close)).index
    sell_idx = df.query('%(column)s >= dc_high_band' % dict(column=close)).index
    df.loc[buy_idx, 'dc_signal'] = 'b'
    df.loc[sell_idx, 'dc_signal'] = 's'

  return df

# Keltner channel (KC)
def add_kc_features(df, n=10, close='Close', open='Open', high='High', low='Low', volume='Volume', method='atr', fillna=False, cal_signal=True):
  """
  Calculate Keltner channel (KC)

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param close: column name of the close
  :param open: column name of the open
  :param high: column name of the high
  :param low: column name of the low
  :param volume: column name of the volume
  :param method: 'atr' or 'ta'
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # calculate keltner channel
  typical_price = (df[high] +  df[low] + df[close]) / 3.0
  middle_band = typical_price.rolling(n, min_periods=0).mean()

  if method == 'atr':
    df = add_atr_features(df=df)
    high_band = middle_band + 2 * df['atr']
    low_band = middle_band - 2 * df['atr']

  else:
    typical_price = ((4*df[high]) - (2*df[low]) + df[close]) / 3.0
    high_band = typical_price.rolling(n, min_periods=0).mean()

    typical_price = ((-2*df[high]) + (4*df[low]) + df[close]) / 3.0
    low_band = typical_price.rolling(n, min_periods=0).mean()

  # fill na values
  if fillna:
    middle_band = middle_band.replace([np.inf, -np.inf], np.nan).fillna(method='backfill')
    high_band = high_band.replace([np.inf, -np.inf], np.nan).fillna(method='backfill')
    low_band = low_band.replace([np.inf, -np.inf], np.nan).fillna(method='backfill')

  # assign values to df
  df['kc_high_band'] = high_band
  df['kc_middle_band'] = middle_band
  df['kc_low_band'] = low_band

  # calculate signals
  if cal_signal:
    df['kc_signal'] = 'n'
    buy_idx = df.query('%(column)s < kc_low_band' % dict(column=close)).index
    sell_idx = df.query('%(column)s > kc_high_band' % dict(column=close)).index
    df.loc[buy_idx, 'kc_signal'] = 'b'
    df.loc[sell_idx, 'kc_signal'] = 's'

  return df



# ================================================ Indicator visualization  ========================================= #
# plot signals on price line
def plot_signal(df, start=None, end=None, price_col='Close', signal_col='signal', pos_signal='b', neg_signal='s', none_signal='n', use_ax=None, figsize=(20, 5), title=None, title_rotation='vertical', title_x=-0.05, title_y=0.3):
  """
  Plot signals along with the price

  :param df: dataframe with price and signal columns
  :param start: start row to plot
  :param end: end row to stop
  :param price_col: columnname of the price values
  :param signal_col: columnname of the signal values
  :param pos_signal: the value of positive signal
  :param neg_siganl: the value of negative signal
  :param none_signal: the value of none signal
  :param use_ax: the already-created ax to draw on
  :param figsize: figsize
  :param title: plot title
  :param title_rotation: 'vertical' or 'horizontal'
  :param title_x: title position x
  :param title_y: title position y
  :returns: a signal plotted price chart
  :raises: none
  """
  # copy dataframe within the specific period
  df = df[start:end]

  # create figure
  ax = use_ax
  if ax is None:
    plt.figure(figsize=figsize)
    ax = plt.gca()

  # plot price and signal
  try:
    ax.plot(df.index, df[price_col], color='black', label=price_col, alpha=0.5)

    # plot signals
    if signal_col in df.columns:
      positive_signal = df.query('%(signal)s == "%(pos_signal)s"' % dict(signal=signal_col, pos_signal=pos_signal))
      negative_signal = df.query('%(signal)s == "%(neg_signal)s"' % dict(signal=signal_col, neg_signal=neg_signal))
      ax.scatter(positive_signal.index, positive_signal[price_col], label='%s' % pos_signal, marker='^', color='green')
      ax.scatter(negative_signal.index, negative_signal[price_col], label='%s' % neg_signal, marker='v', color='red')
  
  except Exception as e:
    print(e)

  # legend and title
  ax.legend(loc='upper left')  
  ax.set_title(title, rotation=title_rotation, x=title_x, y=title_y)

  # return ax
  if use_ax is not None:
    return ax

# plot peack and trough on price line
def plot_peak_trough(df, start=None, end=None, price_col='Close', high_col='High', low_col='Low', signal_col='signal', pos_signal='p', neg_signal='t', none_signal='n', trend_window=4, use_ax=None, figsize=(20, 5), title=None, title_rotation='vertical', title_x=-0.05, title_y=0.3):
  """
  Plot peaks and throughs

  :param df: dataframe with price and signal columns
  :param start: start row to plot
  :param end: end row to stop
  :param price_col: columnname of the price values
  :param high_col: columnname of high vlaues
  :param low_col: columnname of low values
  :param signal_col: columnname of the signal values
  :param pos_signal: the value of positive signal
  :param neg_siganl: the value of negative signal
  :param none_signal: the value of none signal
  :param use_ax: the already-created ax to draw on
  :param figsize: figsize
  :param title: plot title
  :param title_rotation: 'vertical' or 'horizontal'
  :param title_x: title position x
  :param title_y: title position y
  :returns: a signal plotted price chart
  :raises: none
  """
  # copy dataframe within the specific period
  df = df[start:end]

  # create figure
  ax = use_ax
  if ax is None:
    plt.figure(figsize=figsize)
    ax = plt.gca()

  # get peaks and troughs
  peaks = df.query('%(column)s == "%(value)s"' % dict(column=signal_col, value=pos_signal)).copy()
  troughs = df.query('%(column)s == "%(value)s"' % dict(column=signal_col, value=neg_signal)).copy()

  # plot high-low range
  ax.fill_between(df.index, df[high_col], df[low_col], facecolor='blue', interpolate=True, alpha=0.2)

  # plot price
  ax.plot(df.index, df[price_col], label=price_col, color='black', alpha= 0.5)
  
  # plot peak and through
  ax.scatter(peaks.index, peaks[price_col], label='peak', color='green', marker='^', alpha= 0.8)
  ax.scatter(troughs.index, troughs[price_col], label='trough',color='red', marker='v', alpha=0.8)

  # plot trend
  if trend_window is not None and trend_window > 0:

    # calculate slope and intercept for peaks and troughs by linear regression 
    peaks['date'] = peaks.index.astype(str)
    peaks['date_prev'] = peaks['date'].shift(1)
    last_peak = peaks.tail(trend_window).copy()
    last_peak['date_diff'] = last_peak.apply(lambda row: util.num_days_between(row['date_prev'], row['date']), axis=1)
    last_peak['x'] = last_peak['date_diff'].cumsum()

    troughs['date'] = troughs.index.astype(str)
    troughs['date_prev'] = troughs['date'].shift(1)
    last_trough = troughs.tail(trend_window).copy()
    last_trough['date_diff'] = last_trough.apply(lambda row: util.num_days_between(row['date_prev'], row['date']), axis=1)
    last_trough['x'] = last_trough['date_diff'].cumsum()

    peak_lr = linregress(last_peak['x'], last_peak[price_col])
    trough_lr = linregress(last_trough['x'], last_trough[price_col])

    last_peak['y'] = last_peak['x'] * peak_lr[0] + peak_lr[1]
    last_trough['y'] = last_trough['x'] * trough_lr[0] + trough_lr[1]

    ax.plot(last_peak.index, last_peak['y'], label='peak_trend', color='green', linestyle='--', alpha= 0.8)
    ax.plot(last_trough.index, last_trough['y'], label='trough_trend', color='red', linestyle='--', alpha=0.8)

  # legend and title
  ax.set_title(title, rotation=title_rotation, x=title_x, y=title_y)
  ax.legend(loc='upper left')  
  
  if use_ax is not None:
    return ax

# plot ichimoku chart
def plot_ichimoku(df, start=None, end=None, price_col='Close', signal_col='signal', pos_signal='b', neg_signal='s', none_signal='n', use_ax=None, figsize=(20, 5), title=None, title_rotation='vertical', title_x=-0.05, title_y=0.3):
  """
  Plot ichimoku chart

  :param df: dataframe with ichimoku indicator columns
  :param start: start row to plot
  :param end: end row to plot
  :param price_col: columnname of the price
  :param signal_col: columnname of signal values
  :param pos_signal: the value of positive signal
  :param neg_siganl: the value of negative signal
  :param none_signal: the value of none signal
  :param use_ax: the already-created ax to draw on
  :param figsize: figsize
  :param title: plot title
  :param title_rotation: 'vertical' or 'horizontal'
  :param title_x: title position x
  :param title_y: title position y
  :returns: ichimoku plot
  :raises: none
  """
  # copy dataframe within a specific period
  df = df[start:end]

  # create figure
  ax = use_ax
  if ax is None:
    plt.figure(figsize=figsize)
    ax = plt.gca()

  # plot senkou lines
  ax.plot(df.index, df.senkou_a, label='senkou_a', color='green', alpha=0.2)
  ax.plot(df.index, df.senkou_b, label='senkou_b', color='red', alpha=0.2)

  # plot clouds
  ax.fill_between(df.index, df.senkou_a, df.senkou_b, where=df.senkou_a > df.senkou_b, facecolor='green', interpolate=True, alpha=0.1)
  ax.fill_between(df.index, df.senkou_a, df.senkou_b, where=df.senkou_a <= df.senkou_b, facecolor='red', interpolate=True, alpha=0.1)

  # plot kijun/tankan lines
  ax.plot(df.index, df.tankan, label='tankan', color='magenta', linestyle='--')
  ax.plot(df.index, df.kijun, label='kijun', color='blue', linestyle='--')

  # plot price and signal
  ax = plot_signal(df, price_col=price_col, signal_col=signal_col, pos_signal=pos_signal, neg_signal=neg_signal, none_signal=none_signal, use_ax=ax)


  # title and legend
  ax.legend(bbox_to_anchor=(1.02, 0.), loc=3, ncol=1, borderaxespad=0.) 
  ax.set_title(title, rotation=title_rotation, x=title_x, y=title_y)

  if use_ax is not None:
    return ax

# plot general ta indicators
def plot_indicator(df, target_col, start=None, end=None, price_col='Close', signal_col='signal', pos_signal='b', neg_signal='s', none_signal='n', benchmark=None, boundary=None, color_mode=None, use_ax=None, figsize=(20, 5),  title=None, plot_price_in_twin_ax=False, title_rotation='vertical', title_x=-0.05, title_y=0.3):
  """
  Plot indicators around a benchmark

  :param df: dataframe which contains target columns
  :param target_col: columnname of the target indicator
  :param price_col: columnname of the price values
  :param start: start date of the data
  :param end: end of the data
  :param price_col: columnname of the price
  :param signal_col: columnname of signal values
  :param pos_signal: the value of positive signal
  :param neg_siganl: the value of negative signal
  :param none_signal: the value of none signal
  :param benchmark: benchmark, a fixed value
  :param boundary: upper/lower boundaries, a list of fixed values
  :param color_mode: which color mode to use: benckmark/up_down
  :param use_ax: the already-created ax to draw on
  
  :param title: title of the plot
  :param plot_price_in_twin_ax: whether plot price and signal in a same ax or in a twin ax
  :param title_rotation: 'vertical' or 'horizontal'
  :param title_x: title position x
  :param title_y: title position y
  :returns: figure with indicators and close price plotted
  :raises: none
  """
  # select data
  df = df[start:end].copy()
  
  # create figure
  ax = use_ax
  if ax is None:
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111)

  # plot benchmark
  if benchmark is not None:
    df['benchmark'] = benchmark
    ax.plot(df.index, df['benchmark'], color='black', linestyle='--', label='%s'%benchmark, alpha=0.5)

  if boundary is not None:
    if len(boundary) > 0:
      df['upper_boundary'] = max(boundary)
      df['lower_boundary'] = min(boundary)
      ax.plot(df.index, df['upper_boundary'], color='green', linestyle='--', label='%s'% max(boundary), alpha=0.5)
      ax.plot(df.index, df['lower_boundary'], color='red', linestyle='--', label='%s'% min(boundary), alpha=0.5)

  # plot indicator(s)
  unexpected_col = [x for x in target_col if x not in df.columns]
  if len(unexpected_col) > 0:
    print('column not found: ', unexpected_col)
  target_col = [x for x in target_col if x in df.columns]
  for col in target_col:
    ax.plot(df.index, df[col], label=col, alpha=0.8)

  # plot color bars if there is only one indicator to plot
  if len(target_col) == 1:
    tar = target_col[0]

    # plot in up_down mode
    if color_mode == 'up_down':  
      df['color'] = 'red'
      previous_target_col = 'previous_' + tar
      df[previous_target_col] = df[tar].shift(1)
      df.loc[df[tar] > df[previous_target_col], 'color'] = 'green'

    # plot in benchmark mode
    elif color_mode == 'benchmark' and benchmark is not None:
      df['color'] = 'red'
      df.loc[df[tar] > benchmark, 'color'] = 'green'
      
    # plot indicator
    if 'color' in df.columns:
      ax.bar(df.index, height=df[tar], color=df.color, alpha=0.3)

  # plot close price
  if price_col in df.columns:
    if plot_price_in_twin_ax:
      ax2=ax.twinx()
      plot_signal(df, price_col=price_col, signal_col=signal_col, pos_signal=pos_signal, neg_signal=neg_signal, none_signal=none_signal, use_ax=ax2)
      ax2.legend(loc='lower left')
    else:
      plot_signal(df, price_col=price_col, signal_col=signal_col, pos_signal=pos_signal, neg_signal=neg_signal, none_signal=none_signal, use_ax=ax)

  # plot title and legend
  ax.legend(bbox_to_anchor=(1.02, 0.), loc=3, ncol=1, borderaxespad=0.) 
  ax.set_title(title, rotation=title_rotation, x=title_x, y=title_y)

  # return ax
  if use_ax is not None:
    return ax

# plot candlestick charts
def plot_candlestick(df, start=None, end=None, open_col='Open', high_col='High', low_col='Low', close_col='Close', date_col='Date', plot_kama=True, use_ax=None, figsize=(20, 5), title=None, width=0.8, colorup='green', colordown='red', alpha=0.8, title_rotation='vertical', title_x=-0.05, title_y=0.8):
  """
  Plot candlestick data
  :param df: dataframe with ichimoku and mean reversion columns
  :param start: start of the data
  :param end: end of the data
  :param open_col: column name for open values
  :param high_col: column name for high values
  :param low_col: column name for low values
  :param close_col: column name for close values
  :param date_col: column name for date values
  :param plot_kama: whether to plot kama with candlesticks
  :param use_ax: the already-created ax to draw on
  :param figsize: figure size
  :param title: title of the figure
  :param width: width of each candlestick
  :param colorup: color for candlesticks which open > close
  :param colordown: color for candlesticks which open < close
  :param alpha: alpha for charts
  :param title_rotation: 'vertical' or 'horizontal'
  :param title_x: title position x
  :param title_y: title position y
  :returns: plot
  :raises: none
  """
  # select plot data
  df = df[start:end].copy()

  # create figure
  ax = use_ax
  if ax is None:
    plt.figure(figsize=figsize)
    ax = plt.gca()

  # plot_kama
  if set(['kama_fast', 'kama_slow']) < set(df.columns) and plot_kama:
    for k in ['kama_fast', 'kama_slow']:
      ax.plot(df.index, df[k], label=k, alpha=alpha)

  # transform date to numbers
  df.reset_index(inplace=True)
  df[date_col] = df[date_col].apply(mdates.date2num)
  plot_data = df[[date_col, open_col, high_col, low_col, close_col]]
  
  # plot candlesticks
  candlestick_ohlc(ax=ax, quotes=plot_data.values, width=width, colorup=colorup, colordown=colordown, alpha=alpha)
  ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

  # legend and title
  ax.legend(bbox_to_anchor=(1.02, 0.), loc=3, ncol=1, borderaxespad=0.)
  ax.set_title(title, rotation=title_rotation, x=title_x, y=title_y)

  if use_ax is not None:
    return ax

# plot multiple indicators on a same chart
def plot_multiple_indicators(df, args={'plot_ratio': {'ichimoku':1.5, 'mean_reversion':1}, 'mean_reversion': {'std_multiple': 2}}, start=None, end=None, save_path=None, save_image=False, show_image=False, title=None, unit_size=3, ws=0, hs=0.2, title_rotation='horizontal', title_x=0.5, title_y=0.9, subtitle_rotation='vertical', subtitle_x=-0.05, subtitle_y=0.3):
  """
  Plot Ichimoku and mean reversion in a same plot
  :param df: dataframe with ichimoku and mean reversion columns
  :param args: dict of args for multiple plots
  :param start: start of the data
  :param end: end of the data
  :param save_path: path where the figure will be saved to, if set to None, then image will not be saved
  :param show_image: whether to display image
  :param title: title of the figure
  :param unit_size: height of each subplot
  :param ws: wide space 
  :param hs: heighe space between subplots
  :param title_rotation: 'vertical' or 'horizontal'
  :param title_x: title position x
  :param title_y: title position y
  :param subtitle_rotation: 'vertical' or 'horizontal'
  :param subtitle_x: title position x
  :param subtitle_y: title position y
  :returns: plot
  :raises: none
  """
  # select plot data
  plot_data = df[start:end].copy()

  # get indicator names and plot ratio
  plot_ratio = args.get('plot_ratio')
  if plot_ratio is None :
    print('No indicator to plot')
    return None

  indicators = list(plot_ratio.keys())
  ratios = list(plot_ratio.values())
  num_indicators = len(indicators)
  
  # create figures
  fig = plt.figure(figsize=(20, num_indicators*unit_size))  
  gs = gridspec.GridSpec(num_indicators, 1, height_ratios=ratios)
  gs.update(wspace=ws, hspace=hs)

  axes = {}
  for i in range(num_indicators):
    tmp_indicator = indicators[i]
    tmp_args = args.get(tmp_indicator)
    axes[tmp_indicator] = plt.subplot(gs[i]) 
    axes[tmp_indicator].patch.set_alpha(0.5)

    # get extra arguments
    target_col = tmp_args.get('target_col')
    price_col = tmp_args.get('price_col')
    signal_col = tmp_args.get('signal_col')
    pos_signal = tmp_args.get('pos_signal')
    neg_signal = tmp_args.get('neg_signal')
    none_signal = tmp_args.get('none_signal')
    benchmark = tmp_args.get('benchmark')
    boundary = tmp_args.get('boundary')
    color_mode = tmp_args.get('color_mode')
    plot_price_in_twin_ax = tmp_args.get('plot_price_in_twin_ax')
    if plot_price_in_twin_ax is None:
      plot_price_in_twin_ax = False
    
    # plot ichimoku
    if tmp_indicator == 'ichimoku':
      plot_ichimoku(df=plot_data, signal_col=signal_col, title=tmp_indicator, use_ax=axes[tmp_indicator], title_rotation=subtitle_rotation, title_x=subtitle_x, title_y=subtitle_y)

    # plot peak and trough with bollinger band
    elif tmp_indicator == 'peak_trough':
      plot_peak_trough(df=plot_data, signal_col=signal_col, title=tmp_indicator, use_ax=axes[tmp_indicator], title_rotation=subtitle_rotation, title_x=subtitle_x, title_y=subtitle_y)

      add_bbl = tmp_args.get('add_bbl')
      if add_bbl is not None:
        plot_indicator(df=plot_data, target_col=['mavg', 'bb_high_band', 'bb_low_band'], color_mode=None, price_col=None, signal_col=None, use_ax=axes[tmp_indicator], title=tmp_indicator, title_rotation=subtitle_rotation, title_x=subtitle_x, title_y=subtitle_y)
        axes[tmp_indicator].fill_between(plot_data.index, plot_data.mavg, plot_data.bb_high_band, facecolor='green', interpolate=True, alpha=0.1)
        axes[tmp_indicator].fill_between(plot_data.index, plot_data.mavg, plot_data.bb_low_band, facecolor='red', interpolate=True, alpha=0.1)

    elif tmp_indicator == 'candlestick':
      width = tmp_args.get('width')

      if width is None: 
        width = 1
      
      colorup = tmp_args.get('colorup')
      if colorup is None: 
        colorup = 'green'
      
      colordown = tmp_args.get('colordown')
      if colordown is None: 
        colordown = 'red'
      
      alpha = tmp_args.get('alpha')
      if alpha is None:
        alpha = 1

      plot_kama = tmp_args.get('plot_kama')
      if plot_kama is None:
        plot_kama=False
      
      plot_candlestick(df=plot_data, title=tmp_indicator, use_ax=axes[tmp_indicator], plot_kama=plot_kama, width=width, colorup=colorup, colordown=colordown, alpha=alpha, title_rotation=subtitle_rotation, title_x=subtitle_x, title_y=subtitle_y)

    # plot other indicators
    else:
      plot_indicator(
        df=plot_data, target_col=target_col, price_col=price_col, 
        signal_col=signal_col, pos_signal=pos_signal, neg_signal=neg_signal, none_signal=none_signal, 
        benchmark=benchmark, boundary=boundary, color_mode=color_mode,
        title=tmp_indicator, use_ax=axes[tmp_indicator], plot_price_in_twin_ax=plot_price_in_twin_ax, title_rotation=subtitle_rotation, title_x=subtitle_x, title_y=subtitle_y)

  # adjust plot layout
  fig.suptitle(title, rotation=title_rotation, x=title_x, y=title_y, fontsize=20)

  # save image
  if save_image and (save_path is not None):
    plt.savefig(save_path + title + '.png')
    
  # close image
  if not show_image:
    plt.close(fig)




