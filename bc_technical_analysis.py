# -*- coding: utf-8 -*-
"""
Technical Analysis Calculation and Visualization functions

:author: Beichen Chen
"""
import os
import math
import sympy
import datetime
import ta
import numpy as np
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.stats import linregress
from numpy.lib.stride_tricks import as_strided
from matplotlib import gridspec
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

# from mplfinance.original_flavor import candlestick_ohlc
from quant import bc_util as util
from quant import bc_data_io as io_util

# set font for chinese characters 
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei'] 
plt.rcParams['axes.unicode_minus'] = False

# default values
default_ohlcv_col = {'close':'Close', 'open':'Open', 'high':'High', 'low':'Low', 'volume':'Volume'}
default_trend_val = {'pos_trend':'u', 'neg_trend':'d', 'none_trend':'', 'wave_trend':'n'}
default_signal_val = {'pos_signal':'b', 'neg_signal':'s', 'none_signal':'', 'wave_signal': 'n'}

# default indicators and dynamic trend for calculation
default_indicators = {'trend': ['ichimoku', 'kama', 'adx'], 'volume': [], 'volatility': ['bb'], 'other': []}
default_perspectives = ['candle','support_resistant', 'renko']
default_support_resistant_col = ['kama_fast', 'kama_slow', 'tankan', 'kijun', 'candle_gap_top', 'candle_gap_bottom', 'renko_top', 'renko_h', 'renko_l']

# default arguments for visualization
default_candlestick_color = {'color_up':'green', 'color_down':'red', 'shadow_color':'black', 'entity_edge_color':'black', 'alpha':0.8}
default_plot_args = {'figsize':(30, 3), 'title_rotation':'vertical', 'xaxis_position': 'bottom', 'yaxis_position': 'right', 'title_x':-0.01, 'title_y':0.2, 'bbox_to_anchor':(1.02, 0.), 'loc':3, 'ncol':1, 'borderaxespad':0.0}

# zorders
default_zorders = {}
counter = 1
for item in ['default', 'price', 'kama', 'ichimoku', 'renko', 'candle_pattern', 'gap', 'candle_shadow', 'candle_entity', 'extended']:
  default_zorders[item] = counter
  counter += 1

# ================================================ Load configuration =============================================== # 
# load configuration
def load_config(root_paths):
  """ 
  Load configuration from json file

  :param root_paths: a dictionary that contains home_path and git_path (differ by platforms)
  :returns: dictionary of config arguments
  :raises: None
  """
  # copy root paths
  config = root_paths.copy()

  # validate root paths
  for p in config.keys():
    if not os.path.exists(config[p]):
      print(f'{p} not exists!')

  # add derived paths
  config['config_path'] = config['git_path']    +   'quant/'      # github files
  config['quant_path'] = config['home_path']    +   'quant/'      # local files

  config['log_path'] = config['quant_path']     +   'logs/'       # logs of script execution
  config['api_path'] = config['quant_path']     +   'api_key/'    # configuration for data api, etc.
  config['futu_path'] = config['quant_path']    +   'futuopen/'   # configuration for futu platform
  config['tiger_path'] = config['quant_path']   +   'tigeropen/'  # configuration for tiger platform
  config['trader_path'] = config['quant_path']  +   'trader/'     # configuration for trader platforms
  config['data_path'] = config['quant_path']    +   'stock_data/' # downloaded stock data (OHLCV)
  config['result_path'] = config['quant_path']  +   'ta_model/'   # results of script execution
  
  # load self-defined pools (lists of stock symbols)
  config['selected_sec_list'] = io_util.read_config(file_path=config['config_path'], file_name='selected_sec_list.json')

  # load data api
  config['api_key'] = io_util.read_config(file_path=config['api_path'], file_name='api_key.json')

  # load calculation and visulization parameters
  ta_config = io_util.read_config(file_path=config['config_path'], file_name='ta_config.json')
  config.update(ta_config)

  return config

# load locally saved data(sec_data, ta_data, results)
def load_data(target_list, config, interval='day', load_empty_data=False, load_derived_data=False):
  """ 
  Load locally saved data(sec_data, ta_data, results)
  
  :param target_list: list of target pools(each pool is a list of stock symbols)
  :param config: dictionary of config arguments
  :param interval: data interval
  :param load_empty_data: whether to load empyt data dict
  :param load_derived_data: whether to load ta_data, result, final_result besides sec_data
  :returns: dictionary of data load from local files
  :raises: None
  """
  # init data dictionary
  data = {'sec_data': {}, 'ta_data': {}, 'result': {}, 'final_result': {}}
  for target in target_list:
    ti = f'{target}_{interval}'
    data['sec_data'][ti] = {}
    data['ta_data'][ti] = {}
    data['result'][ti] = {}

  # load sec data (data_path/[symbol].csv)
  if not load_empty_data:
    data_path = config['data_path']
    for target in target_list:
      ti = f'{target}_{interval}'
      for symbol in target_list[target]:
        if os.path.exists(data_path+f'{symbol.split(".")[0]}.csv'):
          data['sec_data'][ti][f'{symbol}_day'] = io_util.load_stock_data(file_path=data_path, file_name=symbol, standard_columns=True)
        else:
          data['sec_data'][ti][f'{symbol}_day'] = None

    # load derived data (quant_path/[ta_data/result].pkl)
    if load_derived_data:
      file_path = config["quant_path"]
      for target in target_list:
        ti = f'{target}_{interval}'
        for f in ['ta_data', 'result']:
          file_name = f'{ti}_{f}.pkl'
          if os.path.exists(f'{file_path}{file_name}'):
            data[f][ti] = io_util.pickle_load_data(file_path=file_path, file_name=f'{file_name}')
          else:
            print(f'{file_name} not exists')

  return data


# ================================================ Core progress ==================================================== # 
# preprocess stock data (OHLCV)
def preprocess(df, symbol, print_error=True):
  '''
  Preprocess stock data (OHLCV)

  :param df: downloaded stock data
  :param symbol: symbol of stock
  :param print_error: whether print error information or not
  :returns: preprocessed dataframe
  :raises: None
  '''
  # check whether data is empty or None
  if df is None or len(df) == 0:
    print(f'No data for preprocess')
    return None

  # drop duplicated rows, keep the first
  df = util.remove_duplicated_index(df=df, keep='first')

  # adjust close price manually (if split not updated)
  adj_rate = 1
  df['split_n1'] = df['Split'].shift(-1).fillna(1.0)
  df['adj_close_p1'] = df['Adj Close'].shift(1)
  df['adj_rate'] = df['adj_close_p1'] / df['Adj Close']
  df = df.sort_index(ascending=False)
  for idx, row in df.iterrows():
    df.loc[idx, 'Adj Close'] *= adj_rate
    if row['Split'] != 1.0:
      if row['adj_rate'] >= 1.95 or row['adj_rate'] <= 0.45:
        adj_rate = 1/row['Split']
    elif row['split_n1'] != 1.0:
      if row['adj_rate'] >= 1.95 or row['adj_rate'] <= 0.45:
        adj_rate = 1/row['split_n1']
  df = df.sort_index()
  df.drop(['adj_rate', 'adj_close_p1', 'split_n1'], axis=1, inplace=True)

  # adjust open/high/low/close/volume values
  adj_rate = df['Adj Close'] / df['Close']
  for col in ['High', 'Low', 'Open', 'Close']:
    df[col] = df[col] * adj_rate

  # process NA and 0 values
  max_idx = df.index.max()
  na_cols = []
  zero_cols = []
  error_info = ''

  # check whether 0 or NaN values exists in the latest record
  extra_cols = ['Split', 'Dividend']
  cols = [x for x in df.columns if x not in extra_cols]
  for col in cols:
    if df.loc[max_idx, col] == 0:
      zero_cols.append(col)
    if np.isnan(df.loc[max_idx, col]):
      na_cols.append(col)
    
  # process NaN values
  if len(na_cols) > 0:
    error_info += 'NaN values found in '
    for col in na_cols:
      error_info += f'{col}'
  df['Split'] = df['Split'].fillna(1.0)
  df['Dividend'] = df['Dividend'].fillna(0.0)
  df = df.dropna()
    
  # process 0 values
  if len(zero_cols) > 0:
    error_info += '0 values found in '
    for col in zero_cols:
      error_info += f'{col}'
    df = df[:-1].copy()
  
  # print error information
  if print_error and len(error_info) > 0:
    error_info = f'[{symbol}]: on {max_idx.date()}, {error_info}'
    print(error_info)

  # add symbol and change rate of close price
  df['symbol'] = symbol
  
  return df

# calculate indicators according to definition
def calculate_ta_basic(df, indicators=default_indicators):
  '''
  Calculate indicators according to definition

  :param df: preprocessed stock data
  :param indicators: dictionary of different type of indicators to calculate
  :returns: dataframe with technical indicator columns
  :raises: None
  '''
  # check whether data is empty or None
  if df is None or len(df) == 0:
    print(f'No data for calculate_ta_basic')
    return None  

  # copy dataframe
  df = df.copy()

  # indicator calculation
  indicator = None
  try:
    # calculate close change rate
    phase = 'calculate close rate' 
    df = cal_change_rate(df=df, target_col=default_ohlcv_col['close'], add_accumulation=False)
    
    # calculate candlestick features
    phase = 'calculate candlestick' 
    df = add_candlestick_features(df=df)

    # add indicator features
    phase = 'calculate indicators' 
    indicator_calculated = []
    for i in indicators.keys():
      tmp_indicators = indicators[i]
      for indicator in tmp_indicators:
        if indicator not in indicator_calculated:
          df = eval(f'add_{indicator}_features(df=df)')
          indicator_calculated.append(indicator)
        else:
          print(f'{indicator} already calculated!')

  except Exception as e:
    print(f'[Exception]: @ {phase} - {indicator}, {e}')

  return df

# calculate static trend according to indicators
def calculate_ta_static(df, indicators=default_indicators):
  """
  Calculate static trend according to indicators (which is static to different start/end time).

  :param df: dataframe with several ta features
  :param indicators: dictionary of different type of indicators to calculate
  :returns: dataframe with static trend columns
  :raises: Exception 
  """
  # check whether data is empty or None
  if df is None or len(df) == 0:
    print(f'No data for calculate_ta_static')
    return None
  
  # trend calculation
  try:
    phase = 'calculate trend for trend_indicators'
    
    # ================================ ichimoku/kama trend ====================
    lines = {
      'ichimoku': {'fast': 'tankan', 'slow': 'kijun'}, 
      'kama': {'fast': 'kama_fast', 'slow': 'kama_slow'}}

    for target_indicator in ['ichimoku', 'kama']:
      if target_indicator in indicators['trend']:

        # fast/slow line column names
        fl = lines[target_indicator]['fast']
        sl = lines[target_indicator]['slow']
 
        # distance related column names
        distance = f'{target_indicator}_distance'
        distance_change = f'{target_indicator}_distance_change'
        distance_day = f'{target_indicator}_distance_day'
        trend_col = f'{target_indicator}_trend'

        # distance and distance change(normalized by slow_line)
        df[distance] = df[fl] - df[sl]
        df[distance_change] = df[distance] - df[distance].shift(1)
        df[distance] = df[distance] / df[sl]
        df[distance_change] = df[distance_change] / df[sl]

        # fl/sl change rate and fl & Close, sl & Close crossover
        rate_threshold = 0.001
        for col in [fl, sl]:
          df = cal_change_rate(df=df, target_col=col, periods=1, add_accumulation=False, add_prefix=col, drop_na=False)
          df[f'{col}_day'] = cal_crossover_signal(df=df, fast_line='Close', slow_line=col, pos_signal=1, neg_signal=-1, none_signal=0)
          df[f'{col}_day'] = sda(series=df[f'{col}_day'], zero_as=1)

        # fl & sl crossover  
        fs_day = f'{target_indicator}_fs_day'
        df[fs_day] = cal_crossover_signal(df, fast_line=fl, slow_line=sl, result_col=fs_day, pos_signal='u', neg_signal='d', none_signal='n')
        df[fs_day] = df[fs_day].replace({'u':1, 'd':-1, 'n':0})
        df[fs_day] = sda(series=df[fs_day], zero_as=1)

        # distance signal
        distance_change_threshold = 0.001
        fl_rate_threshold = {'ichimoku': 0.01, 'kama': 0.001}[target_indicator]
        sl_rate_threshold = {'ichimoku': 0, 'kama': 0}[target_indicator]
        conditions = {
          'up': f'({distance} != 0 and {distance_change} > {distance_change_threshold} and {fl}_rate > {fl_rate_threshold}) or ({fl}_rate > 0 and {sl}_rate > 0)',
          'down': f'({distance} != 0 and {distance_change} < {-distance_change_threshold} and {fl}_rate < {fl_rate_threshold}) or ({fl}_rate < 0 and {sl}_rate < 0)',
          'none': f'({-distance_change_threshold} <= {distance_change} <= {distance_change_threshold}) and ({sl}_rate < {sl_rate_threshold})',
        }
        values = {
          'up': 1, 
          'down': -1,
          'none': 0
          }
        df = assign_condition_value(df=df, column=distance_day, condition_dict=conditions, value_dict=values, default_value=0)
        df[distance_day] = sda(series=df[distance_day], zero_as=1).astype(int)
        
        # trend
        rate_threshold = 0.01
        conditions = {
          'up':     f'({distance} > 0)',#f'({distance_day} > 0) and ({distance} > -0.15)', # f'Close > {fl} > {sl}', # f'({fs_day} > 0)', #  
          'down':   f'({distance} < 0)', #f'({distance_day} < 0)', # f'Close < {fl} < {sl}', # f'({fs_day} < 0)' # 
        } 
        values = {
          'up': 'u', 
          'down': 'd',
        }
        df = assign_condition_value(df=df, column=trend_col, condition_dict=conditions, value_dict=values, default_value='n')

    # ichimoku cloud top and bottom
    if 'ichimoku' in indicators['trend']:
      # cloud top and bototm
      green_idx = df.query('ichimoku_fs_day > 0').index
      red_idx = df.query('ichimoku_fs_day < 0').index
      df.loc[green_idx, 'cloud_top'] = df.loc[green_idx, 'tankan']
      df.loc[green_idx, 'cloud_bottom'] = df.loc[green_idx, 'kijun']
      df.loc[red_idx, 'cloud_top'] = df.loc[red_idx, 'kijun']
      df.loc[red_idx, 'cloud_bottom'] = df.loc[red_idx, 'tankan']

    # ================================ aroon trend ============================
    target_indicator = 'aroon'
    if target_indicator in indicators['trend']:
      aroon_col = ['aroon_up', 'aroon_down', 'aroon_gap']
      df[aroon_col] = df[aroon_col].round(1)
      for col in aroon_col:
        df = cal_change(df=df, target_col=col, add_prefix=True, add_accumulation=True)

      # calculate aroon trend
      df['aroon_trend'] = ''

      # it is going up when:
      # 1+. aroon_up is extramely positive(96+)
      # 2+. aroon_up is strongly positive [88,100], aroon_down is strongly negative[0,12]
      up_idx = df.query('(aroon_up>=96) or (aroon_up>=88 and aroon_down<=12)').index
      df.loc[up_idx, 'aroon_trend'] = 'u'

      # it is going down when
      # 1-. aroon_down is extremely positive(96+)
      # 2-. aroon_up is strongly negative[0,12], aroon_down is strongly positive[88,100]
      down_idx = df.query('(aroon_down>=96) or (aroon_down>=88 and aroon_up<=12)').index
      df.loc[down_idx, 'aroon_trend'] = 'd'

      # otherwise up trend
      # 3+. aroon_down is decreasing, and (aroon_up is increasing or aroon_down>aroon_up)
      up_idx = df.query('(aroon_trend!="u" and aroon_trend!="d") and ((aroon_down_change<0) and (aroon_up_change>=0 or aroon_down>aroon_up))').index # and (aroon_up_acc_change_count <= -2 or aroon_down_acc_change_count <= -2)
      df.loc[up_idx, 'aroon_trend'] = 'u'

      # otherwise down trend
      # 3-. aroon_up is decreasing, and (aroon_down is increasing or aroon_up>aroon_down)
      down_idx = df.query('(aroon_trend!="u" and aroon_trend!="d") and ((aroon_up_change<0) and (aroon_down_change>=0 or aroon_up>aroon_down))').index #and (aroon_up_acc_change_count <= -2 or aroon_down_acc_change_count <= -2)
      df.loc[down_idx, 'aroon_trend'] = 'd'

      # it is waving when
      # 1=. aroon_gap keep steady and aroon_up/aroon_down keep changing toward a same direction
      wave_idx = df.query('-32<=aroon_gap<=32 and ((aroon_gap_change==0 and aroon_up_change==aroon_down_change<0) or ((aroon_up_change<0 and aroon_down<=4) or (aroon_down_change<0 and aroon_up<=4)))').index
      df.loc[wave_idx, 'aroon_trend'] = 'n'

      # drop intermediate columns
      df.drop(['aroon_up_change', 'aroon_up_acc_change', 'aroon_up_acc_change_count', 'aroon_down_change', 'aroon_down_acc_change', 'aroon_down_acc_change_count', 'aroon_gap_change', 'aroon_gap_acc_change', 'aroon_gap_acc_change_count'], axis=1, inplace=True)

    # ================================ adx trend ==============================
    target_indicator = 'adx'
    if target_indicator in indicators['trend']:
      
      # adx value and strength
      df['adx_value'] = df['adx_diff_ma']
      df['adx_strength'] = df['adx']
      df = cal_change(df=df, target_col='adx_value', add_accumulation=False, add_prefix=True)
      df = cal_change(df=df, target_col='adx_strength', add_accumulation=False, add_prefix=True)
      df['adx_direction'] = df['adx_value_change'] # sda of adx_value_change
      df['adx_power'] = df['adx_strength_change']  # sda of adx_strength_change
      wave_idx = df.query('-1 < adx_direction < 1 and -0.5 < adx_power < 0.5').index

      # adx_value_prediction
      df['adx_value_prediction'] = df['adx_value'] + em(series=df['adx_value_change'], periods=3).mean()
      df['adx_value_prediction'] = sm(series=df['adx_value_prediction'], periods=5).mean()

      # direction(of value) and power(of strength)
      for col in ['adx_direction', 'adx_power']:
        df.loc[wave_idx, col] = 0
        df[col] = sda(series=df[col], zero_as=0)

        threshold = 0.5
        conditions = {
          'up': f'{col} > {threshold}', 
          'down': f'{col} < {-threshold}', 
          'wave': f'{-threshold} <= {col} <= {threshold}'} 
        values = {
          'up': 1, 
          'down': -1,
          'wave': 0}
        df = assign_condition_value(df=df, column=f'{col}_day', condition_dict=conditions, value_dict=values, default_value=0) 
        df[f'{col}_day'] = sda(series=df[f'{col}_day'], zero_as=1) 

      # whether strength is strong or weak
      adx_strong_weak_threshold = 25
      conditions = {
        'up': f'adx >= {adx_strong_weak_threshold}', 
        'down': f'adx < {adx_strong_weak_threshold}'} 
      values = {
        'up': 1, 
        'down': -1}
      df = assign_condition_value(df=df, column='adx_strong_day', condition_dict=conditions, value_dict=values, default_value=0)
      df['adx_strong_day'] = sda(series=df['adx_strong_day'], zero_as=1)

      # whether value is waving around 0
      adx_wave_threshold = 10
      conditions = {
        'wave': f'{-adx_wave_threshold} <= adx_value <= {adx_wave_threshold}', 
        'none': f'{-adx_wave_threshold} > adx_value or adx_value > {adx_wave_threshold}'} 
      values = {
        'wave': 1, 
        'none': 0}
      df = assign_condition_value(df=df, column='adx_wave_day', condition_dict=conditions, value_dict=values, default_value=0)
      df['adx_wave_day'] = sda(series=df['adx_wave_day'], zero_as=None)

      # highest(lowest) value of adx_value of previous uptrend(downtrend)
      df['prev_adx_value'] = df['adx_value'].shift(1)
      extreme_idx = df.query('adx_direction_day == 1 or adx_direction_day == -1').index.tolist()
      for i in range(len(extreme_idx)):
        tmp_idx = extreme_idx[i]
        if i == 0:
          start = df.index.min()
          end = extreme_idx[i]
        else:
          start = extreme_idx[i-1]
          end = extreme_idx[i]
        tmp_direction = df.loc[tmp_idx, 'adx_direction_day']
        tmp_extreme = df[start:end]['adx_value'].max() if tmp_direction < 0 else df[start:end]['adx_value'].min()
        tmp_direction_start = df.loc[end, 'prev_adx_value']
        df.loc[tmp_idx, 'prev_adx_extreme'] = tmp_extreme
        df.loc[tmp_idx, 'adx_direction_start'] = tmp_direction_start
      df['prev_adx_extreme'] = df['prev_adx_extreme'].fillna(method='ffill')
      df['adx_direction_start'] = df['adx_direction_start'].fillna(method='ffill')

      # overall adx trend
      threshold = 1
      conditions = {
        # adx_direction > 0 and (at least 1)
        # 1. adx_direction > 5
        # 2. adx_value < 0 and adx_power_day < 0
        # 3. adx_value > 0 and adx_power_day > 0
        # 'up': '((adx_direction > 0 and adx_strong_day > 0) and ((adx_direction > 5) or (adx_value < 0 and adx_power_day < 0) or (adx_value > 0 and adx_power_day > 0)))', 
        'up1': '(candle_color == 1 or rate > 0) and (adx_direction > 10 and adx_direction_day > 2)',
        'up2': '(candle_color == 1 or rate > 0) and ((adx_value < 0 and adx_power_day < 0) or (adx_value > 0 and adx_power_day > 0) or (-5 < adx_value < 5 and adx_direction > 0)) and ((adx_direction > 5))',
        # 'up': f'adx_value_change > {threshold}',

        # adx_direction < 0 and (at least 1)
        # 1. adx_direction < -5
        # 2. adx_value > 0 and adx_power_day < 0
        # 3. adx_value < 0 and adx_power_day > 0
        # 'down': '((adx_direction < 0 and adx_strong_day > 0) and ((adx_direction <-5) or (adx_value > 0 and adx_power_day < 0) or (adx_value < 0 and adx_power_day > 0)))',
        'down1': '(adx_direction < -5 and adx_direction_day < -2)', 
        'down2': '((adx_value > 0 and adx_power_day < 0) or (adx_value < 0 and adx_power_day > 0) or (-5 < adx_value < 5 and adx_direction < 0)) and ((adx_direction < -5))',
        # 'down': f'adx_value_change < {-threshold}',

        # at least 1 of following
        # 1. adx_direction in (-5, 5) and (adx_strength_change in (-1, 1) or adx_value_change in (-1, 1) or (adx_power_day in [-1,1] and adx_direction_day in [-1,1]))
        # 2. adx_direction_start in (5, -5) and adx_strong_day in [-1, 1]
        # 'wave': '(((-1 < adx_strength_change < 1) or (-1 < adx_value_change < 1) or (-1 <= adx_power_day <= 1 and -1 <= adx_direction_day <= 1)) and (-5 < adx_direction < 5)) or ((adx_strong_day < 0) and (-5 < adx_direction_start < 5))'
        'wave1': '(-5 <= adx_direction <= 5) and ((-1 <= adx_strength_change <= 1) or (-1 <= adx_value_change <= 1))',
        'wave2': '(-5 <= adx_direction <= 5) and (-1<= adx_power_day <= 1) and (-1 <= adx_direction_day <= 1)',
        'wave3': '(-5 <= adx_direction <= 5) and (-1 <= adx_strong_day <= 1)'
        # 'wave': f'{-threshold} <= adx_value_change <= {threshold}'
      } 
      
      # adx_trend
      values = {
        'up1': 'u', 'up2': 'u', 
        'down1': 'd', 'down2': 'd',
        'wave1': 'n', 'wave2': 'n', 'wave3': 'n'}
      df = assign_condition_value(df=df, column='adx_trend', condition_dict=conditions, value_dict=values, default_value='n') 

      # # conflicted conditions
      # conflicted_idx = df.query('(adx_trend == "u") and (adx_value_change < 0)').index
      # df.loc[conflicted_idx, 'adx_trend'] = 'n'

      # drop redundant column
      df.drop(['prev_adx_value'], axis=1, inplace=True)
  
    # ================================ kst trend ==============================
    target_indicator = 'kst'
    if target_indicator in indicators['trend']:
      conditions = {
        'up': 'kst_diff > 0', 
        'down': 'kst_diff <= 0'} 
      values = {
        'up': 'u', 
        'down': 'd'}
      df = assign_condition_value(df=df, column='kst_trend', condition_dict=conditions, value_dict=values) 
    
    # ================================ cci trend ==============================
    target_indicator = 'cci'
    if target_indicator in indicators['trend']:
      conditions = {
        'up': 'cci_ma > 0', 
        'down': 'cci_ma <= 0'} 
      values = {
        'up': 'u', 
        'down': 'd'}
      df = assign_condition_value(df=df, column='cci_trend', condition_dict=conditions, value_dict=values) 

    # ================================ trix trend =============================
    target_indicator = 'trix'
    if target_indicator in indicators['trend']:
      df['trix_trend'] = 'n'
      up_mask = df['trix'] > df['trix'].shift(1)
      down_mask = df['trix'] < df['trix'].shift(1)
      df.loc[up_mask, 'trix_trend'] = 'u'
      df.loc[down_mask, 'trix_trend'] = 'd'

    # ================================ psar trend =============================
    target_indicator = 'psar'
    if target_indicator in indicators['trend']:
      conditions = {
        'up': 'psar_up > 0', 
        'down': 'psar_down > 0'} 
      values = {
        'up': 'u', 
        'down': 'd'}
      df = assign_condition_value(df=df, column='psar_trend', condition_dict=conditions, value_dict=values, default_value='')

    # ================================ stoch trend =============================
    target_indicator = 'stoch'
    if target_indicator in indicators['trend']:
      conditions = {
        'up': 'stoch_diff > 1 or stoch_k > 80', 
        'down': 'stoch_diff < -1 or stoch_k < 20'} 
      values = {
        'up': 'u', 
        'down': 'd'}
      df = assign_condition_value(df=df, column='stoch_trend', condition_dict=conditions, value_dict=values, default_value='n')

    # =========================================================================

    phase = 'calculate trend for volume_indicators'

    # ================================ eom trend ==============================
    target_indicator = 'eom'
    if target_indicator in indicators['volume']:
      conditions = {
        'up': 'eom_diff > 0', 
        'down': 'eom_diff <= 0'} 
      values = {
        'up': 'u', 
        'down': 'd'}
      df = assign_condition_value(df=df, column='eom_trend', condition_dict=conditions, value_dict=values) 

    # ================================ fi trend ===============================
    target_indicator = 'fi'
    if target_indicator in indicators['volume']:
      conditions = {
        'up': 'fi_ema > 0', 
        'down': 'fi_ema <= 0'} 
      values = {
        'up': 'u', 
        'down': 'd'}
      df = assign_condition_value(df=df, column='fi_trend', condition_dict=conditions, value_dict=values) 

    # =========================================================================
    
    phase = 'calculate trend for volatility_indicators'

    # ================================ bb trend ===============================
    target_indicator = 'bb'
    if target_indicator in indicators['volatility']:
      conditions = {
        'up': 'Close < bb_low_band', 
        'down': 'Close > bb_high_band'} 
      values = {
        'up': 'u', 
        'down': 'd'}
      df = assign_condition_value(df=df, column='bb_trend', condition_dict=conditions, value_dict=values, default_value='')

    # =========================================================================
    
    phase = 'calculate trend for other_indicators'

    # ================================ ao trend ===============================
    target_indicator = 'ao'
    if target_indicator in indicators['other']:
      df['ao_trend'] = 'n'
      up_mask = df['ao'] > df['ao'].shift(1)
      down_mask = df['ao'] < df['ao'].shift(1)
      df.loc[up_mask, 'ao_trend'] = 'u'
      df.loc[down_mask, 'ao_trend'] = 'd'
    
    # =========================================================================

    phase = 'calculate trend overall'

    # ================================ overall trend ==========================
    target_indicator = 'overall'
    if target_indicator > '':
    
      df['up_trend_idx'] = 0
      df['down_trend_idx'] = 0
      df['trend_idx'] = 0
      
      # specify all indicators and specify the exclusives
      all_indicators = []
      for i in indicators.keys():
        all_indicators += [x for x in indicators[i] if x not in all_indicators]

      include_indicators = [x for x in all_indicators if x != 'bb'] # ['ichimoku', 'aroon', 'adx', 'psar']
      for indicator in all_indicators:
        trend_col = f'{indicator}_trend'
        signal_col = f'{indicator}_signal'
        day_col = f'{indicator}_day'

        if trend_col not in df.columns:
          df[trend_col] = 'n'
        if signal_col not in df.columns:
          df[signal_col] = 'n'
        if day_col not in df.columns:
          df[day_col] = 0

        # calculate number of days since trend shifted
        if indicator in ['bb']:
          df[day_col] = sda(series=df[trend_col].replace({'': 0, 'n':0, 'u':1, 'd':-1}).fillna(0), zero_as=1, one_restart=True) 
        else:
          df[day_col] = sda(series=df[trend_col].replace({'': 0, 'n':0, 'u':1, 'd':-1}).fillna(0), zero_as=1) 
        
        # signal of individual indicators are set to 'n'
        if signal_col not in df.columns:
          df[signal_col] = 'n'

        # calculate overall indicator index according to certain important indicators
        if indicator in include_indicators:

          # calculate the overall trend value
          up_idx = df.query(f'{trend_col} == "u"').index
          down_idx = df.query(f'{trend_col} == "d"').index
          df.loc[up_idx, 'up_trend_idx'] += 1
          df.loc[down_idx, 'down_trend_idx'] -= 1

      # calculate overall trend index 
      df['trend_idx'] = df['up_trend_idx'] + df['down_trend_idx']      

  except Exception as e:
    print(f'[Exception]: @ {phase} - {target_indicator}, {e}')
    
  return df

# calculate dynamic trend according to indicators and static trend
def calculate_ta_dynamic(df, perspective=default_perspectives):
  """
  Calculate dynamic trend according to indicators and static trend (which is static to different start/end time).

  :param df: dataframe with technical indicators and their derivatives
  :param perspective: for which indicators[renko, linear, candle, support_resistant], derivative columns that need to calculated 
  :returns: dataframe with dynamic trend columns
  :raises: None
  """
  # check whether data is empty or None
  if df is None or len(df) == 0:
    print(f'No data for calculate_ta_dynamic')
    return None  

  # copy dataframe
  df = df.copy()
  
  # derivatives calculation
  try:

    # ================================ renko analysis ============================
    phase = 'renko analysis'
    if 'renko' in perspective:
      
      # add renko features
      df = add_renko_features(df=df)

      # calculate renko trend
      conditions = {
        'up': '(candle_color == 1) and ((renko_color == "red" and Low > renko_h) or (renko_color == "green"))', 
        'down': '(renko_color == "red") or (renko_color == "green" and Close < renko_l)'} 
      values = {
        'up': 'u', 
        'down': 'd'}
      df = assign_condition_value(df=df, column='renko_trend', condition_dict=conditions, value_dict=values, default_value='n')
      wave_idx = df.query('(renko_trend != "u" and renko_trend != "d") and ((renko_brick_length >= 20 ) and (renko_brick_length>3*renko_duration_p1))').index
      df.loc[wave_idx, 'renko_trend'] = 'n'

      # calculate renko signal
      df['renko_signal'] = 'n'
      df['renko_day'] = sda(series=df['renko_trend'].replace({'': 0, 'n':0, 'u':1, 'd':-1}).fillna(0), zero_as=1)
      
    # ================================ candle analysis ===========================
    phase = 'candle analysis'
    if 'candle' in perspective:
      
      df = add_candlestick_patterns(df=df)

    # ================================ linear analysis ===========================
    phase = 'linear analysis'
    if 'linear' in perspective:
      
      # add linear features
      df = add_linear_features(df=df)

      # crossover signals between Close and linear_fit_high/linear_fit_low, # , 'support', 'resistant'
      for col in ['linear_fit_high', 'linear_fit_low']:
        signal_col = None

        if col in df.columns:
          signal_col = f'{col}_signal'
          df[signal_col] = cal_crossover_signal(df=df, fast_line='Close', slow_line=col, pos_signal=1, neg_signal=-1, none_signal=0)

          if signal_col in df.columns:
            df[signal_col] = sda(series=df[signal_col], zero_as=1)
        else:
          print(f'{col} not in df.columns')
      
      # trends from linear fit 
      # hitpeak or rebound
      conditions = {
        'up': '((linear_fit_low_stop >= 1 and linear_fit_support < candle_entity_bottom) and (Close > linear_fit_low_stop_price))', 
        'down': '((linear_fit_high_stop >= 1 and linear_fit_resistant > candle_entity_top) and (Close < linear_fit_high_stop_price))',
        'wave': '(linear_fit_high_slope == 0 and linear_fit_low_slope == 0)'} 
      values = {
        'up': 'u', 
        'down': 'd',
        'wave': 'n'}
      df = assign_condition_value(df=df, column='linear_bounce_trend', condition_dict=conditions, value_dict=values)
      df['linear_bounce_trend'] = df['linear_bounce_trend'].fillna(method='ffill').fillna('')
      df['linear_bounce_day'] = sda(series=df['linear_bounce_trend'].replace({'': 0, 'n':0, 'u':1, 'd':-1}).fillna(0), zero_as=1)
      
      # break through up or down
      conditions = {
        'up': '((linear_fit_high_stop >= 5 or linear_fit_high_slope == 0) and linear_fit_high_signal >= 1 and ((candle_color == 1 and candle_entity_top > linear_fit_resistant) or (candle_entity_bottom > linear_fit_resistant)))', 
        'down': '((linear_fit_low_stop >= 5 or linear_fit_low_slope == 0) and linear_fit_low_signal <= -1 and ((candle_color == -1 and candle_entity_bottom < linear_fit_support) or (candle_entity_top < linear_fit_support)))'} 
      values = {
        'up': 'u', 
        'down': 'd'}
      df = assign_condition_value(df=df, column='linear_break_trend', condition_dict=conditions, value_dict=values)
      df['linear_break_trend'] = df['linear_break_trend'].fillna(method='ffill').fillna('')
      df['linear_break_day'] = sda(series=df['linear_break_trend'].replace({'': 0, 'n':0, 'u':1, 'd':-1}).fillna(0), zero_as=1)

      # focus on the last row only
      max_idx = df.index.max()
      valid_idxs = df.query('linear_slope == linear_slope').index

    # ================================ support & resistant =======================
    phase = 'support and resistant'
    if 'support_resistant' in perspective:
      df = add_support_resistance(df)

  except Exception as e:
    print(phase, e)

  return df

# calculate all features (ta_data + ta_static + ta_dynamic) all at once
def calculate_ta_feature(df, symbol, start_date=None, end_date=None, indicators=default_indicators):
  """
  Calculate all features (ta_data + ta_static + ta_dynamic) all at once.

  :param df: original dataframe with hlocv features
  :param symbol: symbol of the data
  :param start_date: start date of calculation
  :param end_date: end date of calculation
  :param indicators: dictionary of different type of indicators to calculate
  :returns: dataframe with ta indicators, static/dynamic trend
  :raises: None
  """
  # check whether data is empty or None
  if df is None or len(df) == 0:
    print(f'{symbol}: No data for calculate_ta_feature')
    return None   
  
  try:
    # # preprocess sec_data
    phase = 'preprocess'
    df = preprocess(df=df, symbol=symbol)[start_date:end_date].copy()
    
    # calculate TA indicators
    phase = 'cal_ta_basic_features' 
    df = calculate_ta_basic(df=df, indicators=indicators)

    # calculate TA trend
    phase = 'cal_ta_static_features'
    df = calculate_ta_static(df=df, indicators=indicators)

    # calculate TA derivatives
    phase = 'cal_ta_dynamic_features'
    df = calculate_ta_dynamic(df)


  except Exception as e:
    print(symbol, phase, e)

  return df

# generate description for ta features
def calculate_ta_score(df):
  """
  Generate description for latest ta_data of symbols(aka. result).

  :param df: dataframe which contains latest ta_data of symbols, each row for a symbol
  :raturns: dataframe with description
  :raises: None
  """

  # initialization
  df['trend_score'] = 0
  df['major_score'] = 0
  
  df['trigger_score'] = 0
  df['trigger_score_description'] = ''

  df['position_score'] = 0
  df['position_score_description'] = ''

  df['inday_trend_score'] = 0
  df['inday_trend_score_description'] = ''

  col_to_drop = []

  # ================================ calculate s/m/l trend/score/day ========
  # calculate short/middle/long trend score/day
  trend_conditions = {
    'short': {
      '+adx_value':           [0.5, '', '(adx_direction_day > 1 and adx_direction > 5)'],
      '-adx_value':           [-0.5, '', '(adx_direction_day < -1 and adx_direction < -5)'],
      '+adx_power':           [0.5, '', '(adx_power_day > 1 and adx_value > 0) or (adx_power_day < -1 and adx_value < 0)'],
      '-adx_power':           [-0.5, '', '(adx_power_day > 1 and adx_value < 0) or (adx_power_day < -1 and adx_value > 0)'],
      '+adx_trend':           [1, '', '(adx_trend == "u")'],
      '-adx_trend':           [-1, '', '(adx_trend == "d")'],
      
    },
    'middle': {
      '+tankan':              [0.5, '', '(tankan_rate > 0)'],
      '-tankan':              [-0.5, '', '(tankan_rate <= 0)'],
      '+i_distance_change':   [0.5, '', '(ichimoku_distance_change > 0)'],
      '-i_distance_change':   [-0.5, '', '(ichimoku_distance_change < 0)'],
      '+ichimoku_distance':   [1, '', 'ichimoku_distance > 0'], #  tankan_rate > 0 and 
      '-ichimoku_distance':   [-1, '', 'ichimoku_distance < 0'], # tankan_rate <= 0 and 
    },
    'long': {
      '+kama_fast':           [0.5, '', '(kama_fast_rate > 0)'],
      '-kama_fast':           [-0.5, '', '(kama_fast_rate <= 0)'],
      '+k_distance_change':   [0.5, '', '(kama_distance > 0)'], # kama_fast_rate > 0 and 
      '-k_distance_change':   [-0.5, '', '(kama_distance < 0)'], # kama_fast_rate <= 0 and 
      '+kama_distance':       [1, '', '(kama_distance > 0)'], # kama_fast_rate > 0 and 
      '-kama_distance':       [-1, '', '(kama_distance < 0)'], # kama_fast_rate <= 0 and 
    },
  }
  wave_conditions = {
    'short': [
      '-0.5 <= adx_value_change <= 0.5',
      'adx_strong_day < 0',
      'adx_wave_day > 0',
    ],
    'middle': [
      'ichimoku_distance == 0',
      '-0.01 < ichimoku_distance_change < 0.01',
      'tankan_rate == 0'
    ],
    'long': [
      'kama_distance == 0',
      '-0.01 < kama_distance_change < 0.01',
      'kama_fast_rate == 0'
    ]
  }
  key_columns = {
    'short': 'adx_value_change',
    'middle': 'ichimoku_distance_change',
    'long': 'kama_distance_change'
  }
  term_weight = {'short':1.0, 'middle':0.9, 'long':0.8}
  for term in ['short', 'middle', 'long']:

    # column names
    score_col = f'{term}_trend_score'
    key_col = key_columns[term]

    # term trend score
    trend_condition = trend_conditions[term]
    df = cal_score(df=df, condition_dict=trend_condition, up_score_col=score_col, down_score_col=score_col)
    wave_condition = wave_conditions[term]
    for c in wave_condition:
      tmp_idx = df.query(c).index
      df.loc[tmp_idx, score_col] *= 0.8

    # term trend score += normalized key column score
    df[score_col] += min_max_normalize(df[key_col])

    # major score
    df['major_score'] += (df[score_col] > 0).replace({True: term_weight[term], False: 0})


  # ================================ calculate inday trend ==================
  # inday score and description
  df['prev_candle_entity_top'] = df['candle_entity_top'].shift(1)
  df['prev_candle_entity_bottom'] = df['candle_entity_bottom'].shift(1)
  col_to_drop += ['prev_candle_entity_top', 'prev_candle_entity_bottom']

  s = 0.5
  inday_conditions = {
    
    '+影线':        [s, '', '(candle_lower_shadow_pct > 0.5 and candle_upper_shadow_pct < 0.15)'], # entity_diff > 0.5 and shadow_diff > 1.5 and 
    '-影线':        [-s, '', '(candle_upper_shadow_pct > 0.5 and (candle_lower_shadow_pct < 0.15  or candle_color == -1))'],
    
    '+长实体':      [s, '', '(entity_trend == "u") and (candle_color == 1)'],
    '-长实体':      [-s, '', '(entity_trend == "u") and (candle_color == -1)'],

    '+窗口':        [s, '', '(candle_color == 1 and ((candle_gap == 2) or (相对窗口位置 == "mid_up") or (相对窗口位置 == "out")))'],
    '-窗口':        [-s, '', '((candle_gap == -2) or (相对窗口位置 == "mid_down" or 相对窗口位置 == "mid") or (candle_color == -1 and (相对窗口位置 == "out")))'],
    
    '+触底':        [s, '', '(突破_day == -1 and candle_color == 1)'],
    '-触顶':        [-s, '', '(突破_day == 1 and candle_color == -1)'],

    '+跳升':        [s, '', '(candle_entity_bottom > prev_candle_entity_top)'],
    '-跳降':        [-s, '', '(candle_entity_top < prev_candle_entity_bottom)'],

    '-十字星':      [-s, '', '(十字星_day == -1 or 十字星_day == 1)'],

    '+平头':        [s, '', '(平头_day == 1)'],
    '-平头':        [-s, '', '(平头_day == -1)'],

    '+锤子':        [s, '', '(锤子_day == 1)'],
    '-锤子':        [-s, '', '(锤子_day == -1)'],

    '+腰带':        [s, '', '(腰带_day == 1)'],
    '-腰带':        [-s, '', '(腰带_day == -1)'],

    '+穿刺':        [s, '', '(穿刺_day == 1)'],
    '-穿刺':        [-s, '', '(穿刺_day == -1)'],

    '+启明黄昏':    [s, '', '(启明黄昏_day == 1)'],
    '-启明黄昏':    [-s, '', '(启明黄昏_day == -1)'],
  }
  df = cal_score(df=df, condition_dict=inday_conditions, up_score_col='up_score', down_score_col='down_score')
  df['inday_trend_score'] += df['up_score'] + df['down_score']

  names = {'support':'支撑', 'resistant': '阻挡', 'break_up': '突破', 'break_down': '跌落'}
  for col in ['support', 'resistant', 'break_up', 'break_down']:
    df['inday_trend_score'] += df[f'{col}_score'] * s

    desc = df[f'{col}_description'].apply(lambda x: '' if len(x) == 0 else f'{names[col]}: ' + x + '; ')

    if col in ['support', 'break_up']:
      df['up_score_description'] += desc
    else:
      df['down_score_description'] += desc

  df['inday_trend_score_description'] += df['up_score_description'] + df['down_score_description']

  
  # ================================ calculate trigger/position score =======
  # trigger score and description, position score
  for col in ['tankan_day', 'kama_fast_day', 'kijun_day', 'kama_slow_day']:
    col_desc = '_'.join(col.split('_')[0:-1])
    
    # trigger score
    valid_pos_idx = df.query(f'0 < {col} <= 3').index
    valid_neg_idx = df.query(f'-3 <= {col} < 0').index
    df.loc[valid_pos_idx, 'trigger_score'] += df.loc[valid_pos_idx, col].apply(lambda x: 0 if (np.isnan(x) or x == 0) else 1/x)
    df.loc[valid_neg_idx, 'trigger_score'] += df.loc[valid_neg_idx, col].apply(lambda x: 0 if (np.isnan(x) or x == 0) else 1/x)
    df.loc[valid_pos_idx, 'trigger_score_description'] += f'+{col_desc}, '
    df.loc[valid_neg_idx, 'trigger_score_description'] += f'-{col_desc}, '

    # position score
    valid_pos_idx = df.query(f'0 < {col}').index
    valid_neg_idx = df.query(f'{col} < 0').index
    df.loc[valid_pos_idx, 'position_score'] += 1
    df.loc[valid_neg_idx, 'position_score'] += -1
    df.loc[valid_pos_idx, 'position_score_description'] += f'+{col_desc}, '
    df.loc[valid_neg_idx, 'position_score_description'] += f'-{col_desc}, '

  df['trigger_score_description'] = df['trigger_score_description'].apply(lambda x: x[:-2])
  df['position_score_description'] = df['position_score_description'].apply(lambda x: x[:-2])

  position_conditions = {
    'pos':    f'trigger_score > 0.0', 
    'neg':    f'trigger_score < 0.0',
  } 
  position_values = {
    'pos':    1, 
    'neg':    -1,
  }
  df = assign_condition_value(df=df, column='trigger_day', condition_dict=position_conditions, value_dict=position_values, default_value=0)
  df['trigger_day'] = sda(series=df['trigger_day'], zero_as=1)
  
  # trigger_score when at high(position_score == 4) or low(position_score == -4) position
  none_trigger_high = df.query('position_score == 4 and trigger_score == 0 and candle_color == 1').index
  df.loc[none_trigger_high, 'trigger_score'] = df.loc[none_trigger_high, 'candle_entity_pct']

  none_trigger_low = df.query('position_score == -4 and trigger_score == 0 and  candle_color == -1').index
  df.loc[none_trigger_low, 'trigger_score'] = df.loc[none_trigger_low, 'candle_entity_pct'] * -1


  # ================================ calculate trend score ==================
  # overall score
  weights = {'inday': 0.2, 'short': 0.4, 'middle': 0.2, 'long': 0.2}
  for term in ['inday', 'short', 'middle', 'long']:
    score_col = f'{term}_trend_score'
    df['trend_score'] += df[score_col] * weights[term]

  # drop redundant columns
  for col in col_to_drop:
    if col in df.columns:
      df.drop(col, axis=1, inplace=True)

  return df

# calculate signal according to features
def calculate_ta_signal(df):
  """
  Calculate signal according to features.

  :param df: dataframe with ta features and derived features for calculating signals
  :raturns: dataframe with signal
  :raises: None
  """

  if df is None or len(df) == 0:
    print(f'No data for calculate_ta_signal')
    return None

  # add ta score and description
  df = calculate_ta_score(df)
  
  # ================================ calculate trend ========================
  for term in ['inday', 'short', 'middle', 'long', '']:
    
    trend_col = f'{term}_trend' if term != '' else 'trend'
    score_col = f'{term}_trend_score' if term != '' else 'trend_score'
    day_col = f'{term}_day' if term != '' else 'trend_day'

    df[score_col] = df[score_col].round(2)

    # term trend
    term_trend_conditions = {
      'up':     f'{score_col} > 0.1', 
      'down':   f'{score_col} < -0.1',
    } 
    term_trend_values = {
      'up':     'u', 
      'down':   'd',
    }
    df = assign_condition_value(df=df, column=trend_col, condition_dict=term_trend_conditions, value_dict=term_trend_values, default_value='n')

    # term trend day
    df[day_col] = sda(df[trend_col].replace({"u":1, "d":-1, "n":0}), zero_as=1)

    # term trend score change
    df = cal_change(df=df, target_col=score_col, periods=1, add_accumulation=False, add_prefix=True)

  # ================================ calculate potential ====================
  # label score
  df['potential'] = ''
  df['potential_score'] = 0
  df['potential_description'] = ''
  potential_conditions = {
    '触发':         f'(((0 < trigger_day < 5 and trigger_score > 0.3) or (trigger_day == 1)) and (trend_score_change > 0 and (trend_score > 0 or (trend_score > -0.5 and short_day > 0)))) ',
    '超卖':         f'(0 < bb_day < 5 and candle_color == 1)'
    } 
  for c in potential_conditions.keys():
    tmp_condition = potential_conditions[c]
    tmp_idx = df.query(tmp_condition).index
    df.loc[tmp_idx, 'potential'] = 'potential'
    df.loc[tmp_idx, 'potential_score'] += 1
    df.loc[tmp_idx, 'potential_description'] += f'{c}, '

  # remove false alarm
  none_potential_idx = []
  none_potential_conditions = {
    '价格下跌':       f'potential == "potential" and ((rate < -0.05) or (shadow_trend == "u" and upper_shadow_trend == "u") or (candle_color == -1 and entity_trend == "u"))',
    '短暂反弹':       f'potential == "potential" and ((adx_diff_ma < 0 and (adx_direction_day == 1 or (adx_direction_day < 0 and adx_value_change > 0) or adx_value_change < 0)) and ((ichimoku_distance <= 0 or ichimoku_distance_day <= -3) and (kama_distance <= 0 or kama_distance_day <= -3)))',
    '趋势下降':       f'potential == "potential" and ((trend_score == -3) or (trend_score < 0 and trigger_score <= 0))',
    } 

  if 'linear_slope' in df.columns:
    none_potential_conditions['linear wave'] = f'potential == "potential" and (linear_fit_high_slope == 0 and linear_fit_low_slope == 0)'

  for c in none_potential_conditions.keys():
    tmp_condition = none_potential_conditions[c]
    tmp_idx = df.query(tmp_condition).index
    none_potential_idx += tmp_idx.tolist()
    df.loc[tmp_idx, 'potential_score'] += -1
    df.loc[tmp_idx, 'potential_description'] += f'{c}, '
  none_potential_idx = list(set(none_potential_idx))
  df.loc[none_potential_idx, 'potential'] = ''
  df['potential_description'] = df['potential_description'].apply(lambda x: x[:-2])

  # ================================ calculate signal =======================
  # signal
  df['signal'] = ''
  df['signal_description'] = ''
  df['signal_day'] = 0

  # conditions = {
  #   'buy':          '(trend_score_change > 0 and trigger_score > 0)',
  #   'sell':         '(trend_score_change < 0 and trigger_score < 0)',
  # } 
  # values = {
  #   'buy':          'b',
  #   'sell':         's',
  # }
  # df = assign_condition_value(df=df, column='signal', condition_dict=conditions, value_dict=values, default_value='')

  # # disable some false alarms
  # none_signal_idx = []
  # none_signal_conditions = {
  #   # '趋势不明':        '(signal == "b") and ((inday_trend_score < 0 and potential != "potential") or (trend_score < 0.5 and short_day == 1))',
  #   # '短期趋势下降':     '(signal == "b") and ((short_trend_score < -1 and inday_trend_score <= 0))',
  #   # '整体趋势波动':     '(signal == "b") and (trend_score < 0.5 and major_score < 0)',
  #   # '超卖':             '(signal == "b") and (bb_day == -1)and ((inday_trend_score <=0 or major_score < 3) or (trend_score_change < 0 and inday_trend_score < 0))',
  #   # '低位波动':         '(signal == "b") and (position_score == -4)',
  #   '弱势波动':         '(signal == "b") and ((-10 < adx_direction_start < 10) and (adx_strong_day < 0) and (adx_direction < 5 or adx_value_change < 0.1))',
  # } 
  # for c in none_signal_conditions.keys():
  #   tmp_condition = none_signal_conditions[c]
  #   tmp_idx = df.query(tmp_condition).index
  #   none_signal_idx += tmp_idx.tolist()
  #   df.loc[tmp_idx, 'signal_description'] += f'{c}, '
  # none_signal_idx = list(set(none_signal_idx))
  # df.loc[none_signal_idx, 'signal'] = ''
  # df['signal_description'] = df['signal_description'].apply(lambda x: x[:-2])

  # # calculate signal day
  # df['signal_day'] = sda(df['signal'].replace({'b': 1, 's': -1, '': 0}), zero_as=1)
  # df = remove_redundant_signal(df=df, signal_col='signal', pos_signal='b', neg_signal='s', none_signal='', keep='first')

  return df

# visualize features and signals
def visualization(df, start=None, end=None, interval='day', title=None, save_path=None, visualization_args={}):
  """
  Visualize features and signals.

  :param df: dataframe with ta indicators
  :param start: start date to draw
  :param end: end date to draw
  :param title: title of the plot
  :param save_path: to where the plot will be saved
  :param visualization_args: arguments for plotting
  :returns: None
  :raises: Exception
  """
  if df is None or len(df) == 0:
    print(f'No data for visualization')
    return None

  try:
    # visualize 
    phase = 'visualization'
    is_show = visualization_args.get('show_image')
    is_save = visualization_args.get('save_image')
    plot_args = visualization_args.get('plot_args')
    
    plot_multiple_indicators(
      df=df, title=title, args=plot_args,  start=start, end=end, interval=interval,
      show_image=is_show, save_image=is_save, save_path=save_path)
  except Exception as e:
    print(phase, e)

# postprocess
def postprocess(df, keep_columns, drop_columns, sec_names, target_interval=''):
  """
  Postprocess

  :param df: dataframe with ta features and ta derived features
  :param keep_columns: columns to keep for the final result
  :param drop_columns: columns to drop for the final result
  :param watch_columns: list of indicators to keep watching
  :returns: postprocessed dataframe
  :raises: None
  """

  if df is None or len(df) == 0:
    print(f'No data for postprocess')
    return pd.DataFrame()

  # reset index(as the index(date) of rows are all the same)
  df = df.reset_index().copy()

  # overbuy/oversell
  df['obos'] = df['bb_trend'].replace({'d': '超买', 'u': '超卖', 'n': ''})

  # sort symbols
  df = df.sort_values(['adx_day', 'adx_value', 'adx_direction_day', 'prev_adx_extreme'], ascending=[True, True, True, True])

  # add names for symbols
  df['name'] = df['symbol']
  df['name'] = df['name'].apply(lambda x: sec_names[x])

  # rename columns, keep 3 digits
  df = df[list(keep_columns.keys())].rename(columns=keep_columns).round(3)
  
  # add target-interval info
  df['ti'] = target_interval

  # drop columns
  df = df.drop(drop_columns, axis=1)
  
  return df


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
def filter_idx(df, condition_dict):
  """
  # Filter index that meet conditions

  :param df: dataframe to search
  :param condition_dict: dictionary of conditions
  :returns: dictionary of index that meet corresponding conditions
  :raises: None
  """
  # target index
  result = {}
  for condition in condition_dict.keys():
    result[condition] = df.query(condition_dict[condition]).index

  # other index
  other_idx = df.index
  for i in result.keys():
    other_idx = [x for x in other_idx if x not in result[i]]
  result['other'] = other_idx

  return result

# set value to column of indeies that meet specific conditions
def assign_condition_value(df, column, condition_dict, value_dict, default_value=None):
  """
  # set value to column of index that meet conditions

  :param df: dataframe to search
  :param column: target column
  :param condition_dict: dictionary of conditions
  :param value_dict: corresponding value to assign to the column
  :param default_value: default value of the column
  :returns: dataframe with the column set
  :raises: None
  """
  # copy dataframe
  df = df.copy()
  
  # set default value of column
  if default_value is not None:
    df[column] = default_value
  
  # set condition value to filterd index
  filtered_idx = filter_idx(df=df, condition_dict=condition_dict)
  for k in value_dict.keys():
    condition_idx = filtered_idx.get(k)
    condition_value = value_dict[k]

    if condition_idx is None:
      print(f'{k} not found in filter')
    else:
      df.loc[condition_idx, column] = condition_value
  
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

# weighted moving average
def wma(series, periods, fillna=False):
  """
  Weighted monving average from simple moving window

  :param series: series to calculate
  :param periods: size of the moving window
  :param fillna: make the min_periods = 0
  :returns: a rolling weighted average of 'series' with window size 'periods'
  :raises: none
  """
  weight = pd.Series([i * 2 / (periods * (periods + 1)) for i in range(1, periods + 1)])
  weighted_average = sm(series=series, periods=periods).apply(lambda x: (weight * x).sum(), raw=True)
  return weighted_average

# same direction accumulation
def sda(series, zero_as=None, one_restart=False):
  """
  Accumulate value with same symbol (+/-), once the symbol changed, start over again

  :param series: series to calculate
  :param accumulate_by: if None, accumulate by its own value, other wise, add by specified value
  :param zero_val: action when encounter 0: if None pass, else add(minus) spedicied value according to previous symbol 
  :returns: series with same direction accumulation
  :raises: None
  """
  # copy series
  target_col = series.name
  index_col = series.index.name
  new_series = series.reset_index()

  if index_col is None:
    print('please assigan a name to index column')

  previous_idx = None
  current_idx = None
  for index, row in new_series.iterrows():
    
    # record current index
    current_idx = index

    # for the first loop
    if previous_idx is None:
      pass
    
    # for the rest of loops
    else:
      current_val = new_series.loc[current_idx, target_col]
      previous_val = new_series.loc[previous_idx, target_col]

      if current_val * previous_val > 0:
        if one_restart and current_val in [1, -1]:
          new_series.loc[current_idx, target_col] = current_val

        else:
          new_series.loc[current_idx, target_col] = current_val + previous_val
      
      # current value is 0 and previous value is not 0
      elif current_val == 0 and previous_val != 0:
        if zero_as is not None:
          if previous_val > 0:
            new_series.loc[current_idx, target_col] = previous_val + zero_as
          else: 
            new_series.loc[current_idx, target_col] = previous_val - zero_as

      # otherwise(different direction, previous(and current) value is 0)
      else:
        pass

    # record previous index
    previous_idx = index

  # reset index back
  if index_col is not None:
    new_series = new_series.set_index(index_col)[target_col].copy()
  else:
    new_series = new_series[target_col].copy()

  return new_series

# moving slope
def moving_slope(series, periods):
  """
  Moving Slope

  :param series: series to calculate
  :param periods: size of the moving window
  :returns: a tuple of series: (slope, intercepts)
  :raises: none
  """  
  # convert series to numpy array
  np_series = series.to_numpy()
  stride = np_series.strides
  slopes, intercepts = np.polyfit(np.arange(periods), as_strided(np_series, (len(series)-periods+1, periods), stride+stride).T, deg=1)

  # padding NaNs on the top
  padding_nan = np.full((periods-1, ), np.nan)
  padded_slopes = np.concatenate([padding_nan, slopes])
  padded_intercepts = np.concatenate([padding_nan, intercepts])
  
  return (padded_slopes, padded_intercepts)

# normilization
def normalize(series, fillna=None):
  normalaized = series
  if fillna is not None:  
    normalaized = series.fillna(method=fillna)

  normalaized = (normalaized - normalaized.min()) / (normalaized.max() - normalaized.min())
  return normalaized

# min-max normalization
def min_max_normalize(series, fillna=None):
  normalized = normalize(series, fillna)
  normalized = normalized * 2 - 1

  return normalized


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
  :returns: dataframe with change columns
  :raises: none
  """
  # copy dateframe
  df = df.copy()

  # set prefix for result columns
  prefix = ''
  if add_prefix:
    prefix = f'{target_col}_'

  # set result column names
  change_col = f'{prefix}change'
  acc_change_col = f'{prefix}acc_change'
  acc_change_count_col = f'{prefix}acc_change_count'

  # calculate change within the period
  df[change_col] = df[target_col].diff(periods=periods)
  
  # calculate accumulative change in a same direction
  if add_accumulation:

    df[acc_change_col] = sda(series=df[change_col], zero_as=0)

    df[acc_change_count_col] = 0
    df.loc[df[change_col]>0, acc_change_count_col] = 1
    df.loc[df[change_col]<0, acc_change_count_col] = -1
    df[acc_change_count_col] = sda(series=df[acc_change_count_col], zero_as=1)
    
  # drop NA values
  if drop_na:        
    df.dropna(inplace=True)

  return df 

# calculate change rate of a column in certain period
def cal_change_rate(df, target_col, periods=1, add_accumulation=True, add_prefix=False, drop_na=False):
  """
  Calculate change rate of a column with a sliding window
  
  :param df: original dataframe
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
    prefix = f'{target_col}_'

  # set result column names
  rate_col = f'{prefix}rate'
  acc_rate_col = f'{prefix}acc_rate'
  acc_day_col = f'{prefix}acc_day'

  # calculate change rate within the period
  df[rate_col] = df[target_col].pct_change(periods=periods)
  
  # calculate accumulative change rate in a same direction
  if add_accumulation:
    df[acc_rate_col] = 0
    df.loc[df[rate_col]>=0, acc_day_col] = 1
    df.loc[df[rate_col]<0, acc_day_col] = -1

    # add continuous values which has the same symbol (+/-)
    df[acc_rate_col] = sda(series=df[rate_col], zero_as=0)
    df[acc_day_col] = sda(series=df[acc_day_col], zero_as=1)

    # fill NA in acc_day_col with 0
    df[acc_rate_col] = df[acc_rate_col].fillna(0.0)
    df[acc_day_col] = df[acc_day_col].fillna(0).astype(int) 
  if drop_na:        
    df.dropna(inplace=True) 

  return df

# calculate score according to conditions
def cal_score(df, condition_dict, up_score_col, down_score_col):

  # initialization
  if up_score_col not in df.columns:
    df[up_score_col] = 0
  if down_score_col not in df.columns:
    df[down_score_col] = 0
  
  df[f'{up_score_col}_description'] = ''
  df[f'{down_score_col}_description'] = ''

  # extract score, label and condition from dict
  labels = {}
  scores = {}
  conditions = {}
  for k in condition_dict.keys():
    scores[k] = condition_dict[k][0]
    labels[k] = condition_dict[k][1]
    conditions[k] = condition_dict[k][2]
  
  # calculate score and score_description
  for c in conditions.keys():
    tmp_idx = df.query(conditions[c]).index
    
    # scores
    if c[0] == '+':
      df.loc[tmp_idx, up_score_col] += scores[c]
      df.loc[tmp_idx, f'{up_score_col}_description'] += f'{c}, '
    elif c[0] == '-':
      df.loc[tmp_idx, down_score_col] +=scores[c]
      df.loc[tmp_idx, f'{down_score_col}_description'] += f'{c}, '
    else:
      print(f'{c} not recognized')

  df[up_score_col] = df[up_score_col].round(2)
  df[down_score_col] = df[down_score_col].round(2)

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
  :param neg_signal: the value of negative signal
  :param none_signal: the value of none signal
  :returns: series of the result column
  :raises: none
  """
  df = df.copy()

  # calculate the distance between fast and slow line
  df['diff'] = df[fast_line] - df[slow_line]
  df['diff_prev'] = df['diff'].shift(1)

  # get signals from fast/slow lines cross over
  conditions = {
    'up': '(diff >= 0 and diff_prev < 0) or (diff > 0 and diff_prev <= 0)', 
    'down': '(diff <= 0 and diff_prev > 0) or (diff < 0 and diff_prev >= 0)'} 
  values = {
    'up': pos_signal, 
    'down': neg_signal}
  df = assign_condition_value(df=df, column=result_col, condition_dict=conditions, value_dict=values, default_value=none_signal)
  
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
  conditions = {
    'up': f'{upper_col} > {upper_boundary}', 
    'down': f'{lower_col} < {lower_boundary}'} 
  values = {
    'up': pos_signal, 
    'down': neg_signal}
  df = assign_condition_value(df=df, column=result_col, condition_dict=conditions, value_dict=values, default_value=none_signal)

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
  signals = df.query(f'{signal_col} != "{none_signal}"').copy()
  movement = {'first': 1, 'last': -1}.get(keep)

  # find duplicated signals and set to none_signal
  if len(signals) > 0 and movement is not None:
    signals['is_dup'] = signals[signal_col] + signals[signal_col].shift(movement)
    dup_idx = signals.query(f'is_dup == "{pos_signal}{pos_signal}" or is_dup == "{neg_signal}{neg_signal}"').index

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
    ma_col = f'{target_col}_ma_{mw}'
    df[ma_col] = mw_func(series=df[target_col], periods=mw).mean()
  
  return df

# add candle stick features 
def add_candlestick_features(df, ohlcv_col=default_ohlcv_col):
  """
  Add candlestick dimentions for dataframe

  :param df: original OHLCV dataframe
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :returns: dataframe with candlestick columns
  :raises: none
  """
  # copy dataframe
  df = df.copy()

  # set column names
  open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']
  
  # candle color
  df['candle_color'] = 0
  up_idx = df[open] < df[close]
  down_idx = df[open] >= df[close]
  df.loc[up_idx, 'candle_color'] = 1
  df.loc[down_idx, 'candle_color'] = -1
  
  # shadow
  df['candle_shadow'] = (df[high] - df[low])
  
  # entity
  df['candle_entity'] = abs(df[close] - df[open])
  
  # ======================================= shadow/entity ============================================ #
  df['candle_entity_top'] = 0
  df['candle_entity_bottom'] = 0
  df.loc[up_idx, 'candle_entity_top'] = df.loc[up_idx, close]
  df.loc[up_idx, 'candle_entity_bottom'] = df.loc[up_idx, open]
  df.loc[down_idx, 'candle_entity_top'] = df.loc[down_idx, open]  
  df.loc[down_idx, 'candle_entity_bottom'] = df.loc[down_idx, close]

  df['candle_upper_shadow'] = df[high] - df['candle_entity_top']
  df['candle_lower_shadow'] = df['candle_entity_bottom'] - df[low]

  df['candle_upper_shadow_pct'] = df['candle_upper_shadow'] / df['candle_shadow']
  df['candle_lower_shadow_pct'] = df['candle_lower_shadow'] / df['candle_shadow']
  df['candle_entity_pct'] = df['candle_entity'] / df['candle_shadow']
  df['candle_entity_middle'] = (df['candle_entity_top'] + df['candle_entity_bottom']) * 0.5

  # ======================================= gap ====================================================== #
  # gap_up / gap_down
  col_to_drop = [] 
  for col in [open, close, high, low, 'candle_color', 'candle_entity']:
    prev_col = f'prev_{col}' 
    df[prev_col] = df[col].shift(1)
    col_to_drop.append(prev_col)
  
  # initialization
  df['candle_gap'] = 0
  df['candle_gap_color'] = 0
  df['candle_gap_top'] = np.NaN
  df['candle_gap_bottom'] = np.NaN
  
  # gap up
  df['low_prev_high'] = df[low] - df[f'prev_{high}']
  gap_up_idx = df.query(f'low_prev_high > 0').index
  df.loc[gap_up_idx, 'candle_gap'] = 1
  gap_up_mean = df.loc[gap_up_idx, 'low_prev_high'].mean() # df['low_prev_high'].nlargest(10).values[-1] # 
  gap_up_mean = 0 if np.isnan(gap_up_mean) else gap_up_mean
  strict_gap_up_idx = df.query(f'low_prev_high >= {gap_up_mean} and low_prev_high > 0').index
  if len(strict_gap_up_idx) / len(df) < 0.05:
    df.loc[strict_gap_up_idx, 'candle_gap'] = 2
    df.loc[strict_gap_up_idx, 'candle_gap_color'] = 1
    df.loc[strict_gap_up_idx, 'candle_gap_top'] = df.loc[strict_gap_up_idx, f'{low}']
    df.loc[strict_gap_up_idx, 'candle_gap_bottom'] = df.loc[strict_gap_up_idx, f'prev_{high}']
  
  # gap down
  df['prev_low_high'] = df[f'prev_{low}'] - df[high]
  gap_down_idx = df.query(f'prev_low_high > 0').index  
  df.loc[gap_down_idx, 'candle_gap'] = -1
  gap_down_mean = df.loc[gap_down_idx, 'prev_low_high'].mean() # df['prev_low_high'].nlargest(10).values[-1] # 
  gap_down_mean = 0 if np.isnan(gap_down_mean) else gap_down_mean
  strict_gap_down_idx = df.query(f'prev_low_high >= {gap_down_mean} and prev_low_high > 0').index  
  if len(strict_gap_down_idx) / len(df) < 0.05:
    df.loc[strict_gap_down_idx, 'candle_gap'] = -2
    df.loc[strict_gap_down_idx, 'candle_gap_color'] = -1
    df.loc[strict_gap_down_idx, 'candle_gap_top'] = df.loc[strict_gap_down_idx, f'prev_{low}']
    df.loc[strict_gap_down_idx, 'candle_gap_bottom'] = df.loc[strict_gap_down_idx, f'{high}']
  
  # gap height, color, top and bottom
  # df['candle_gap_height'] = df['candle_gap_top'] - df['candle_gap_bottom']
  df['candle_gap_top'] = df['candle_gap_top'].fillna(method='ffill') 
  df['candle_gap_bottom'] = df['candle_gap_bottom'].fillna(method='ffill') 
  df['candle_gap_color'] = df['candle_gap_color'].fillna(method='ffill')
  # df['candle_gap_height'] = df['candle_gap_height'].fillna(method='ffill')
  
  # drop intermidiate columns
  for c in ['low_prev_high', 'prev_low_high']:
    col_to_drop.append(c)
  df = df.drop(col_to_drop, axis=1)

  return df

# add candle stick patterns
def add_candlestick_patterns(df, ohlcv_col=default_ohlcv_col):

  # global position
  if 'position' > '':

    conditions = {
      # 实体中部 > tankan/kijun/kama_fast/kama_slow
      '顶部': '(candle_entity_middle > kijun and candle_entity_middle > kama_slow and candle_entity_middle > tankan and candle_entity_middle > kama_fast)', 
      # 实体中部 < tankan/kijun/kama_fast/kama_slow
      '底部': '(candle_entity_middle < kijun and candle_entity_middle < kama_slow and candle_entity_middle < tankan and candle_entity_middle < kama_fast)'}
    values = {'顶部': 'u', '底部': 'd'}
    df = assign_condition_value(df=df, column='位置_trend', condition_dict=conditions, value_dict=values, default_value='n')
    df['位置_day'] = df['位置_trend'].replace({'u':1, 'd':-1, 'n':0}).fillna(0).astype(int)
    df['位置_day'] = sda(series=df['位置_day'], zero_as=1)
    
    df['moving_max'] = sm(series=df['High'], periods=10).max()
    df['moving_min'] = sm(series=df['Low'], periods=10).min()
    
    conditions = {
      # 位置_trend == "u", 近10日最高价
      '顶部': '(位置_trend == "u" and moving_max == High)', 
      # 位置_trend == "d", 近10日最低价
      '底部': '(位置_trend == "d" and moving_min == Low)'}
    values = {'顶部': 'u', '底部': 'd'}
    df = assign_condition_value(df=df, column='极限_trend', condition_dict=conditions, value_dict=values, default_value='n')
    
  # shadow and entity
  if 'shadow_entity' > '':

    # X_diff: (X-mean(X, 30))/std(X, 30)
    ma_period = 30
    std_factor = 0.7
    for col in ['entity', 'shadow']:
      df[f'{col}_ma'] = sm(series=df[f'candle_{col}'], periods=ma_period).mean()
      df[f'{col}_std'] = sm(series=df[f'candle_{col}'], periods=ma_period).std()
      df[f'{col}_diff'] = (df[f'candle_{col}'] - df[f'{col}_ma'])/df[f'{col}_std']

    # long/short shadow
    conditions = {
      '价格波动范围大': f'shadow_diff >= {std_factor}', 
      '价格波动范围小': f'shadow_diff <= {-std_factor}'}
    values = {'价格波动范围大': 'u', '价格波动范围小': 'd'}
    df = assign_condition_value(df=df, column='shadow_trend', condition_dict=conditions, value_dict=values, default_value='n')

    # long/short entity
    conditions = {
      '长实体': f'(entity_diff >= {2*std_factor}) or (entity_diff >= {std_factor} and (shadow_trend == "u" and candle_entity_pct >= 0.8))', 
      '短实体': f'(entity_diff <= {-std_factor})'} 
    values = {'长实体': 'u', '短实体': 'd'}
    df = assign_condition_value(df=df, column='entity_trend', condition_dict=conditions, value_dict=values, default_value='n')

    # long/short upper/lower shadow
    for col in ['upper', 'lower']:
      conditions = {
        '长影线': f'(candle_{col}_shadow_pct > 0.3)', 
        '短影线': f'(candle_{col}_shadow_pct < 0.1)'}
      values = {'长影线': 'u', '短影线': 'd'}
      df = assign_condition_value(df=df, column=f'{col}_shadow_trend', condition_dict=conditions, value_dict=values, default_value='n')

  # gaps between candles
  if 'windows' > '':

    # remove those which have too many gaps
    up_gap_idxs = df.query('candle_gap == 2').index.tolist()
    down_gap_idxs = df.query('candle_gap == -2').index.tolist()
    if len(up_gap_idxs) > 10:
      up_gap_idxs = []
    if len(down_gap_idxs) > 10:
      down_gap_idxs = []

    # window(gap)
    conditions = {
      '向上跳空': 'candle_gap > 1', 
      '向下跳空': 'candle_gap < -1'}
    values = {'向上跳空': 'u', '向下跳空': 'd'}
    df = assign_condition_value(df=df, column='窗口_trend', condition_dict=conditions, value_dict=values, default_value='n')

    # window position status (beyond/below/among window)
    conditions = {
      '上方': '(candle_entity_bottom >= candle_gap_top)',
      '中上': '((candle_entity_top > candle_gap_top) and (candle_gap_top > candle_entity_bottom >= candle_gap_bottom))',
      '中间': '((candle_entity_top <= candle_gap_top) and (candle_entity_bottom >= candle_gap_bottom))',
      '穿刺': '((candle_entity_top > candle_gap_top) and (candle_entity_bottom < candle_gap_bottom))',
      '中下': '((candle_entity_bottom < candle_gap_bottom) and (candle_gap_top >= candle_entity_top > candle_gap_bottom))',
      '下方': '(candle_entity_top <= candle_gap_bottom)'}
    values = {
      '上方': 'up', '中上': 'mid_up',
      '中间': 'mid', '穿刺': 'out',
      '中下': 'mid_down', '下方': 'down'}
    df = assign_condition_value(df=df, column='相对窗口位置', condition_dict=conditions, value_dict=values, default_value='')

    # break through up or down
    df['prev_相对窗口位置'] = df['相对窗口位置'].shift(1)
    conditions = {
      '向上突破': f'(candle_gap != 2) and (相对窗口位置 == "up" and prev_相对窗口位置 in {["mid_up", "out", "mid", "mid_down", "down"]})',
      '向下突破': f'(candle_gap != -2) and (相对窗口位置 == "down" and prev_相对窗口位置 in {["mid_down", "out", "mid", "mid_up", "up"]})'
    }
    values = {'向上突破': 'u', '向下突破': 'd'}
    df = assign_condition_value(df=df, column='突破_trend', condition_dict=conditions, value_dict=values, default_value='n')
  
  # patterns that consist only 1 candlestick
  if '1_candle' > '':
    # cross
    conditions = {
      # # -0.5 <= 影线σ <= 0.5, 实体占比 < 1%
      # '波动': '(-0.5 <= shadow_diff <= 0.5) and (candle_entity_pct < 0.15)',
      # # 影线σ < -0.5, 非长影线, 短实体, 长上影线, 长下影线, 实体占比 < 10%
      # '十字星': '(shadow_diff < -0.5) and (entity_trend == "d" and (upper_shadow_trend == "u" or lower_shadow_trend == "u")) and (shadow_trend != "u" and candle_entity_pct <= 0.1)',
      # # 影线σ > 0.5, 长影线, 短实体, 长上影线, 长下影线, 实体占比 < 20%
      # '高浪线': '(shadow_diff >= 0.5) and (entity_trend == "d" and upper_shadow_trend == "u" and lower_shadow_trend == "u") and (shadow_trend == "u" and candle_entity_pct <= 0.2)'

      '十字星_1': '(candle_entity_pct < 0.15) and (shadow_diff < -1.5)',
      '高浪线': '(candle_entity_pct < 0.15) and (shadow_diff > -1.5)',
      '十字星_2': '(candle_entity_pct < 0.05)',
      }
    values = {'十字星_1': 'd', '高浪线': 'u', '十字星_2': 'd', } # '波动': 'd', 
    df = assign_condition_value(df=df, column='十字星', condition_dict=conditions, value_dict=values, default_value='n')

    # hammer/meteor
    conditions = {
      # 影线σ > 1, 长下影线, 非长实体, 上影线占比 < 5%, 实体占比 <= 30%, 下影线占比 >= 60%
      '锤子': '(shadow_diff > 1) and (upper_shadow_trend == "d" and entity_trend != "u") and (candle_upper_shadow_pct < 0.05 and 0.05 <= candle_entity_pct <= 0.3 and candle_lower_shadow_pct >= 0.6)',
      # 影线σ > 1, 长上影线, 非长实体, 上影线占比 >= 60%, 实体占比 <= 30%, 下影线占比 < 5%
      '流星': '(shadow_diff > 1) and (lower_shadow_trend == "d" and entity_trend != "u") and (candle_upper_shadow_pct >= 0.6 and 0.05 <= candle_entity_pct <= 0.3 and candle_lower_shadow_pct < 0.05)'}
    values = {'锤子': 'u', '流星': 'd'}
    df = assign_condition_value(df=df, column='锤子', condition_dict=conditions, value_dict=values, default_value='n')

    # cross/highwave
    conditions = {
      # 位置_trend in ['u', 'd'], 形态 == '十字星'
      '十字星': '(十字星 == "d")', #(位置_trend != "n") and 
      # 位置_trend in ['u', 'd'], 形态 == '高浪线'
      '高浪线': '(十字星 == "u")'} # (位置_trend != "n") and 
    values = {'十字星': 'd', '高浪线': 'u'}
    df = assign_condition_value(df=df, column='十字星_trend', condition_dict=conditions, value_dict=values, default_value='n')

    # belt
    conditions = {
      # 非短实体, 低位, 价格上涨, 实体占比 > 50%, 下影线占比 <= 5%, 上影线占比 >= 15%
      '看多腰带': '(entity_trend != "d" and candle_entity_pct > 0.5) and (位置_trend == "d" and candle_lower_shadow_pct <= 0.05 and candle_upper_shadow_pct >= 0.15 and candle_color == 1)',
      # 非短实体, 高位, 价格下跌, 实体占比 > 50%, 上影线占比 <= 5%, 下影线占比 >= 15%
      '看空腰带': '(entity_trend != "d" and candle_entity_pct > 0.5) and (位置_trend == "u" and candle_upper_shadow_pct <= 0.05 and candle_lower_shadow_pct >= 0.15 and candle_color == -1)'}
    values = {'看多腰带': 'u', '看空腰带': 'd'}
    df = assign_condition_value(df=df, column='腰带_trend', condition_dict=conditions, value_dict=values, default_value='n')

    # meteor
    conditions = {
      # 高位, 近10日最高, 形态 == '流星'
      '流星线': '(极限_trend == "u") and (锤子 == "d")',
      # 低位, 近10日最低, 形态 == '流星'
      '倒锤线': '(极限_trend == "d") and (锤子 == "d")'}
    values = {'流星线': 'd', '倒锤线': 'u'}
    df = assign_condition_value(df=df, column='流星_trend', condition_dict=conditions, value_dict=values, default_value='n')

    # hammer
    conditions = {
      # 高位, 近10日最高, 形态 == '锤子'
      '吊颈线': '(极限_trend == "u") and (锤子 == "u")',
      # 低位, 近10日最低, 形态 == '锤子'
      '锤子线': '(极限_trend == "d") and (锤子 == "u")'}
    values = {
      '吊颈线': 'd', '锤子线': 'u'}
    df = assign_condition_value(df=df, column='锤子_trend', condition_dict=conditions, value_dict=values, default_value='n')
    
  # patterns that consist multiple candlesticks
  if 'multi_candle' > '':

    # initialize multi-candle pattern trend
    idxs = df.index.tolist()
    for t in ['平头', '穿刺', '吞噬', '包孕', '启明黄昏']:
      df[f'{t}_trend'] = 'n'

    # flat top/bottom
    df['high_diff'] = ((df['High'] - df['High'].shift(1)) / df['Close']).abs()
    df['low_diff'] = ((df['Low'] - df['Low'].shift(1)) / df['Close']).abs()
    df['candle_upper_shadow_pct_diff'] = df['candle_upper_shadow_pct'] - df['candle_upper_shadow_pct'].shift(1)
    conditions = {
      # 非十字星/高浪线, adx趋势向上(或高位), 高位, [1.近10日最高, 顶部差距<0.2%, 2.顶部差距<0.1%, 3.顶部差距<0.4%, 价格下跌, 上影线差距在5%内]
      'flat top': '(十字星 == "n") and (adx_day > 0 or adx_value > 15) and ((极限_trend == "u" and high_diff <= 0.002) or (位置_trend == "u" and ((high_diff <= 0.001) or (high_diff <= 0.004 and rate <= 0 and -0.05 <= candle_upper_shadow_pct_diff <= 0.05))))',
      # 非十字星/高浪线, adx趋势向下(或低位), 低位, 近10日最低, 底部差距<0.2%
      'flat bottom': '(十字星 == "n") and (adx_day < 0 or adx_value < -15) and (极限_trend == "d") and (low_diff <= 0.002)'}
    values = {'flat top': 'd', 'flat bottom': 'u'}
    df = assign_condition_value(df=df, column='平头_trend', condition_dict=conditions, value_dict=values, default_value='n')

    # iterate through dataframe by window_size of 2 and 3
    previous_row = None
    previous_previous_row = None
    for idx in idxs:
      
      # current row(0), previous row(-1) 
      row = df.loc[idx]
      previous_i = idxs.index(idx) - 1
      if previous_i < 0:
        continue
      else:
        previous_idx = idxs[previous_i]
        previous_row = df.loc[previous_idx]

      # previous previous row(-2)
      previous_previous_i = previous_i - 1
      if previous_previous_i < 0:
        previous_previous_row = None
      else:
        previous_previous_idx = idxs[previous_previous_i]
        previous_previous_row = df.loc[previous_previous_idx]

      # 当前蜡烛非短实体, 实体占比 > 75%
      if row['entity_trend'] == 'd' or row['candle_entity_pct'] < 0.75:
        pass
      else:
        # =================================== 吞噬形态 ==================================== #
        if (previous_row['candle_entity_top'] < row['candle_entity_top']) and (previous_row['candle_entity_bottom'] > row['candle_entity_bottom']):
        
          # 空头吞噬: 位于顶部, 1-绿, 2-红
          if (row['极限_trend'] == "u"):
            if (previous_row['candle_color'] == 1 and row['candle_color'] == -1):
              df.loc[idx, '吞噬_trend'] = 'd'

          # 多头吞噬: 位于底部, 1-红, 2-绿
          elif (row['极限_trend'] == "d"):
            if (previous_row['candle_color'] == -1 and row['candle_color'] == 1):
              df.loc[idx, '吞噬_trend'] = 'u'

      # 前一蜡烛非短实体, 实体占比 > 75%
      if previous_row['entity_trend'] == 'd' or previous_row['candle_entity_pct'] < 0.75:
        pass
      else:
        # =================================== 包孕形态 ==================================== #
        if (previous_row['candle_entity_top'] > row['candle_entity_top']) and (previous_row['candle_entity_bottom'] < row['candle_entity_bottom']) and (previous_row['High'] > row['High']) and (previous_row['Low'] < row['Low']):
          
          # 空头包孕: 位于顶部, 1-绿, 2-红
          if row['极限_trend'] == 'u':
            if (previous_row['candle_color'] == 1 and row['candle_color'] == -1):
              df.loc[idx, '包孕_trend'] = 'd'

          # 多头包孕: 位于底部, 1-红, 2-绿
          elif row['极限_trend'] == 'd':
            if (previous_row['candle_color'] == -1 and row['candle_color'] == 1):
              df.loc[idx, '包孕_trend'] = 'u'
      
      # 顶部:乌云盖顶, 黄昏星
      if (previous_row['位置_trend'] == "u"):

        # =================================== 乌云盖顶  =================================== #
        # 1-必须为绿色, 2-必须为红色长实体
        if (row['位置_trend'] != 'u' or row['entity_trend'] == 'd' or row['candle_color'] == 1 or previous_row['candle_color'] == -1 or previous_row['entity_trend'] == "d"):
          pass
        else:
          # 顶部>前顶部, 底部>前底部, 底部穿过前中点
          if (previous_row['candle_entity_top'] < row['candle_entity_top']) and (previous_row['candle_entity_middle'] > row['candle_entity_bottom']): # and (previous_row['candle_entity_middle'] > row['candle_entity_bottom'])
            df.loc[idx, '穿刺_trend'] = 'd'

        # =================================== 黄昏星  ===================================== #
        if previous_previous_row is None:
          pass
        else:
          # 1-绿色, 2-高位, 3-红色
          if (previous_row['位置_trend'] == "u") and (previous_previous_row['candle_color'] == 1) and (row['candle_color'] == -1):
            # 3-长实体 或 3-middle > 1-middle 
            if row['entity_trend'] == 'u' or (row['candle_entity_middle'] < previous_previous_row['candle_entity_middle']):
              # 2-小实体, 2-底部 > 1/3-顶部
              if (previous_row['entity_trend'] == 'd') and (previous_row['candle_entity_bottom'] > previous_previous_row['candle_entity_top']) and (previous_row['candle_entity_bottom'] > row['candle_entity_top']): #(previous_row['High'] > previous_previous_row['High']) and (previous_row['High'] > row['High']):
                df.loc[idx, '启明黄昏_trend'] = 'd'
              # 2-非小实体, 2-底部 > 1/3-顶部
              elif (previous_row['entity_trend'] == 'n') and (previous_row['candle_entity_bottom'] > previous_previous_row['candle_entity_top']) and (previous_row['candle_entity_bottom'] > row['candle_entity_top']):
                  df.loc[idx, '启明黄昏_trend'] = 'd'

      # 底部:穿刺形态, 启明星
      elif (previous_row['位置_trend'] == "d"):

        # =================================== 穿刺形态  =================================== #
        # 1-必须为红色, 2-必须为绿色长实体
        if (row['位置_trend'] != 'd' or row['entity_trend'] != 'u' or row['candle_color'] == -1 or previous_row['candle_color'] == 1):
          pass
        else:
          # 顶部<=前顶部, 底部<前底部, 顶部穿过前中点
          if (previous_row['candle_entity_top'] >= row['candle_entity_top']) and (previous_row['candle_entity_bottom'] > row['candle_entity_bottom']) and (previous_row['candle_entity_middle'] < row['candle_entity_top']):
            df.loc[idx, '穿刺_trend'] = 'u'
        
        # =================================== 启明星  ===================================== #
        if previous_previous_row is None:
          pass
        else:
          # 1-红色非小实体, 2-高位, 3-绿色非小实体
          if (previous_row['极限_trend'] == "d") and (previous_previous_row['entity_trend'] != 'd') and (row['candle_color'] == 1 and row['entity_trend'] != 'd'):
            # 3-长实体 或 3-middle > 1-top 
            if row['entity_trend'] == 'u' or (row['candle_entity_middle'] > previous_previous_row['candle_entity_top']):
              # 2-小实体, 2-顶部 < 1/3-底部
              if (previous_row['entity_trend'] == 'd') and (previous_row['candle_entity_top'] < previous_previous_row['candle_entity_bottom']) and (previous_row['candle_entity_top'] < row['candle_entity_bottom']): #(previous_row['Low'] < previous_previous_row['Low']) and (previous_row['Low'] < row['Low']):
                df.loc[idx, '启明黄昏_trend'] = 'u'
              # 2-非小实体, 2-顶部 < 1/3-底部
              elif (previous_row['entity_trend'] == 'n') and (previous_row['candle_entity_top'] < previous_previous_row['candle_entity_bottom']) and (previous_row['candle_entity_top'] < row['candle_entity_bottom']):
                  df.loc[idx, '启明黄昏_trend'] = 'u'

  # days since signal triggered
  all_candle_patterns = ['窗口', '突破', '十字星', '流星', '锤子', '腰带', '平头', '穿刺', '包孕', '吞噬', '启明黄昏'] # '反弹', 
  for col in all_candle_patterns:
    df[f'{col}_day'] = df[f'{col}_trend'].replace({'u':1, 'd':-1, 'n':0, '': 0}).fillna(0).astype(int)
    df[f'{col}_day'] = sda(series=df[f'{col}_day'], zero_as=1, one_restart=True)

    # # continuous same trend
    # u_mask = df.query(f'{col}_trend == "u"').index
    # d_mask = df.query(f'{col}_trend == "d"').index
    # df.loc[u_mask, f'{col}_day'] = 1
    # df.loc[d_mask, f'{col}_day'] = -1
  
  # redundant intermediate columns
  for col in [
    'recent_high', 'recent_low',
    'prev_相对窗口位置', 'high_diff', 'low_diff', 'candle_upper_shadow_pct_diff', 'candle_lower_shadow_pct_diff', 
    'entity_ma', 'entity_std', 'shadow_ma', 'shadow_std', # 'shadow_diff', 'entity_diff',
    
    'moving_max', 'moving_min']:
    if col in df.columns:
      df.drop(col, axis=1, inplace=True)

  return df

# add heikin-ashi candlestick features
def add_heikin_ashi_features(df, ohlcv_col=default_ohlcv_col, replace_ohlc=False, dropna=True):
  """
  Add heikin-ashi candlestick dimentions for dataframe

  :param df: original OHLCV dataframe
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :returns: dataframe with candlestick columns
  :raises: none
  """
  # copy dataframe
  df = df.copy()

  # set column names
  open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

  # add previous stick
  columns_to_drop = []
  for col in [open, high, low, close]:
    tmp_col = f'prev_{col}'
    df[tmp_col] = df[col].shift(1)
    columns_to_drop.append(tmp_col)

  # calculate heikin-ashi ohlc
  df['H_Close'] = (df[open] + df[high] + df[low] + df[close])/4
  df['H_Open'] = (df[f'prev_{open}'] + df[f'prev_{close}'])/2
  df['H_High'] = df[[f'prev_{high}', 'H_Open', 'H_Close']].max(axis=1)
  df['H_Low'] = df[[f'prev_{low}', 'H_Open', 'H_Close']].min(axis=1)
    
  # replace original ohlc with heikin-ashi ohlc
  if replace_ohlc:
    for col in [open, high, low, close]:
      df.drop(f'{col}', axis=1, inplace=True)
    df.rename(columns={'H_Close': close, 'H_Open': open, 'H_High': high, 'H_Low': low}, inplace=True)

  # dropna values
  if dropna:
    df.dropna(inplace=True)

  # drop redundant columns
  for col in columns_to_drop:
    df.drop(col, axis=1, inplace=True)
  
  return df

# linear regression for recent high and low values
def add_linear_features(df, max_period=60, min_period=5, is_print=False):

  # get all indexes
  idxs = df.index.tolist()

  # get current date, renko_color, earliest-start date, latest-end date
  current_date = df.index.max()
  earliest_start = idxs[-60] if len(idxs) >= 60 else idxs[0] # df.tail(max_period).index.min()
  latest_end = idxs[-2]
  # if (idxs[-1] - idxs[-2]).days >= 7:
  #   latest_end = idxs[-2]
  # else:
  #   latest_end = current_date - datetime.timedelta(days=(current_date.weekday()+1))
  if is_print:
    print(earliest_start, latest_end)

  # recent high/low 
  recent_period = int(max_period / 2)
  possible_idxs = df[:latest_end].index.tolist()
  middle_high = df[possible_idxs[-recent_period]:latest_end]['High'].idxmax()
  long_high = df[possible_idxs[-max_period]:latest_end]['High'].idxmax()
  middle_low =  df[possible_idxs[-recent_period]:latest_end]['Low'].idxmin()
  long_low = df[possible_idxs[-max_period]:latest_end]['High'].idxmin()

  # get slice of data
  start = earliest_start
  end = latest_end
  candidates = [middle_high, middle_low, long_high, long_low]
  start_candidates = [x for x in candidates if x < possible_idxs[-min_period]]
  start_candidates.sort(reverse=True)
  end_candidates = [x for x in candidates if x > possible_idxs[-min_period]]
  if len(end_candidates) > 0:
    end = max(end_candidates)
  if len(start_candidates) > 0:
    for s in start_candidates:
      if (end-s).days > min_period:
        start = s
        break
  if is_print:
    print(start, end)

  # get peaks and troughs
  tmp_data = df[start:end].copy()
  tmp_idxs = tmp_data.index.tolist()
  
  # gathering high and low points for linear regression
  high = {'x':[], 'y':[]}
  low = {'x':[], 'y':[]}
  for ti in tmp_idxs:
    x = idxs.index(ti)
    y_high = df.loc[ti, 'High']  
    y_low = df.loc[ti, 'Low']  
    high['x'].append(x)
    high['y'].append(y_high)
    low['x'].append(x)
    low['y'].append(y_low)

  # linear regression for high/low values
  highest_high = df[start:latest_end]['High'].max()
  highest_high_idx = tmp_data['High'].idxmax()
  lowest_low = df[start:latest_end]['Low'].min()
  lowest_low_idx = tmp_data['Low'].idxmin()

  # high linear regression
  if len(high['x']) < 2: 
    high_linear = (0, highest_high, 0, 0)
  else:
    high_linear = linregress(high['x'], high['y'])
    high_range = round((max(high['y']) + min(high['y']))/2, 3)
    slope_score = round(abs(high_linear[0])/high_range, 5)
    if slope_score < 0.001:
      high_linear = (0, highest_high, 0, 0)

  # low linear regression
  if len(low['x']) < 2:
    low_linear = (0, lowest_low, 0, 0)
  else:
    low_linear = linregress(low['x'], low['y'])
    low_range = round((max(low['y']) + min(low['y']))/2, 3)
    slope_score = round(abs(low_linear[0])/low_range, 5)
    if slope_score < 0.001:
      low_linear = (0, lowest_low, 0, 0)

  # add high/low fit values
  counter = 0
  idx_max = len(idxs)
  idx_min = min(min(high['x']), min(low['x']))
  std_ma = df[idx_min:idx_max]['Close'].std()
  for x in range(idx_min, idx_max):
    
    idx = idxs[x]
    counter += 1
    df.loc[idx, 'linear_day_count'] = counter

    # predicted high/low values    
    linear_fit_high = high_linear[0] * x + high_linear[1] + 0.3 * std_ma
    linear_fit_low = low_linear[0] * x + low_linear[1] - 0.3 * std_ma

    # linear fit high
    df.loc[idx, 'linear_fit_high_slope'] = high_linear[0]
    if (linear_fit_high <= highest_high and linear_fit_high >= lowest_low): 
      df.loc[idx, 'linear_fit_high'] = linear_fit_high
    elif linear_fit_high > highest_high:
      df.loc[idx, 'linear_fit_high'] = highest_high
    elif linear_fit_high < lowest_low:
      df.loc[idx, 'linear_fit_high'] = lowest_low
    else:
      df.loc[idx, 'linear_fit_high'] = np.NaN
    
    # if  high_linear[0] > 0 and idx > highest_high_idx and df.loc[idx, 'linear_fit_high'] <= highest_high:
    #   df.loc[idx, 'linear_fit_high'] = highest_high

    # linear fit low
    df.loc[idx, 'linear_fit_low_slope'] = low_linear[0]
    if (linear_fit_low <= highest_high and linear_fit_low >= lowest_low): 
      df.loc[idx, 'linear_fit_low'] = linear_fit_low
    elif linear_fit_low > highest_high:
      df.loc[idx, 'linear_fit_low'] = highest_high
    elif linear_fit_low < lowest_low:
      df.loc[idx, 'linear_fit_low'] = lowest_low
    else:
      df.loc[idx, 'linear_fit_low'] = np.NaN

    # if  low_linear[0] < 0 and idx > lowest_low_idx and df.loc[idx, 'linear_fit_low'] >= lowest_low:
    #   df.loc[idx, 'linear_fit_low'] = lowest_low

  # high/low fit stop
  df['linear_fit_high_stop'] = 0
  df['linear_fit_low_stop'] = 0
  reach_top_idx = df.query(f'High=={highest_high} and linear_fit_high_slope >= 0').index
  reach_bottom_idx = df.query(f'Low=={lowest_low} and linear_fit_low_slope <= 0').index
  df.loc[reach_top_idx, 'linear_fit_high_stop'] = 1
  df.loc[reach_top_idx, 'linear_fit_high_stop_price'] = df.loc[reach_top_idx, 'candle_entity_bottom']
  df.loc[reach_bottom_idx, 'linear_fit_low_stop'] = 1
  df.loc[reach_bottom_idx, 'linear_fit_low_stop_price'] = df.loc[reach_bottom_idx, 'candle_entity_top']
  for col in ['linear_fit_high_stop', 'linear_fit_high_stop_price', 'linear_fit_low_stop', 'linear_fit_low_stop_price']:
    df[col] = df[col].fillna(method='ffill')
    if col in ['linear_fit_high_stop', 'linear_fit_low_stop']:
      df[col] = sda(df[col], zero_as=1)

  # support and resistant
  resistant_idx = df.query(f'linear_fit_high == {highest_high} and linear_fit_high_stop > 0').index
  if len(resistant_idx) > 0:
    df.loc[min(resistant_idx), 'linear_fit_resistant'] = highest_high
  else:
    df['linear_fit_resistant'] = np.nan

  support_idx = df.query(f'linear_fit_low == {lowest_low} and linear_fit_low_stop > 0').index
  if len(support_idx) > 0:
    df.loc[min(support_idx), 'linear_fit_support'] = lowest_low
  else:
    df['linear_fit_support'] = np.nan

  for col in ['linear_fit_support', 'linear_fit_resistant']:
    df[col] = df[col].fillna(method='ffill')

  # overall slope of High and Low
  df['linear_slope']  = df['linear_fit_high_slope'] + df['linear_fit_low_slope']

  # direction means the slopes of linear fit High/Low
  conditions = {
    'up': '(linear_fit_high_slope > 0 and linear_fit_low_slope > 0) or (linear_fit_high_slope > 0 and linear_fit_low_slope == 0) or (linear_fit_high_slope == 0 and linear_fit_low_slope > 0)', 
    'down': '(linear_fit_high_slope < 0 and linear_fit_low_slope < 0) or (linear_fit_high_slope < 0 and linear_fit_low_slope == 0) or (linear_fit_high_slope == 0 and linear_fit_low_slope < 0)',
    'none': '(linear_fit_high_slope > 0 and linear_fit_low_slope < 0) or (linear_fit_high_slope < 0 and linear_fit_low_slope > 0) or (linear_fit_high_slope == 0 and linear_fit_low_slope == 0)'} 
  values = {
    'up': 'u', 
    'down': 'd',
    'none': 'n'}
  df = assign_condition_value(df=df, column='linear_direction', condition_dict=conditions, value_dict=values, default_value='')
        
  return df
 
# linear regression for recent kama and ichimoku fast slow lines
def add_ma_linear_features(df, period=5, target_col=['kama_fast', 'kama_slow', 'tankan', 'kijun']):

  result = {}
  
  for col in target_col:
    if col in df.columns:
      y = df[col].tail(period).values.tolist()
      x = list(range(1, period+1))
      reg_result = linregress(x, y)
      result[col] = reg_result
    else:
      continue

  return result

# kama and ichimoku fast/slow line support and resistance
def add_support_resistance(df, target_col=default_support_resistant_col, perspective=default_perspectives):
  """
  Add support and resistance 

  :param df: dataframe with ta features
  :param target_col: column that support or resistant price
  :returns: dataframe with support or resistance columns
  :raises: none
  """
  # copy dataframe
  df = df.copy()
  col_to_drop = []

  # remove columns that not exists
  target_col = [x for x in target_col if x in df.columns]

  # calculate middle price
  df['mid_price'] = (df['High'] + df['Low']) / 2
  col_to_drop.append('mid_price')

  generated_cols = {'High': [], 'Low': []}
  # calculate support and resistance
  for col_1 in ['High', 'Low']:
    for col_2 in target_col:
      
      # calculate mutual distnace
      distance_col = f'{col_1}_to_{col_2}'
      col_to_drop.append(distance_col)

      tmp_distance = abs(df[col_1] - df[col_2]) / df[col_1]
      df[distance_col] = tmp_distance
      generated_cols[col_1].append(distance_col)
      
  # column_name = {'h_2_gt': 'candle_gap_top', 'h_2_gb': 'candle_gap_bottom', 'l_2_gt': 'candle_gap_top', 'l_2_gb': 'candle_gap_bottom'}
  df['support_score'] = 0
  df['support_description'] = ''
  df['resistant_score'] = 0
  df['resistant_description'] = ''
  df['break_up_score'] = 0
  df['break_up_description'] = ''
  df['break_down_score'] = 0
  df['break_down_description'] = ''

  # ================================ intra-day support and resistant ===================
  # calculate support
  distance_threshold = 0.005
  shadow_pct_threhold = 0.20
  for col in generated_cols['Low']:
    tmp_col = col.split('_to_')[-1]
    support_idx = df.query(f'(十字星_day != 1 and 十字星_day != -1) and ((candle_color == 1 and mid_price > {tmp_col}) or (candle_color == -1 and Close > {tmp_col})) and (candle_lower_shadow_pct > {shadow_pct_threhold} or candle_lower_shadow_pct > candle_upper_shadow_pct) and ({col} < {distance_threshold})').index.tolist()
    df.loc[support_idx, 'support_description'] += f'{tmp_col}, '

  # calculate resistance
  for col in generated_cols['High']:
    tmp_col = col.split('_to_')[-1]
    resistant_idx = df.query(f'(十字星_day != 1 and 十字星_day != -1) and ((candle_color == -1 and mid_price < {tmp_col}) or (candle_color == 1 and Close < {tmp_col})) and (candle_upper_shadow_pct > {shadow_pct_threhold} or candle_upper_shadow_pct > candle_lower_shadow_pct) and ({col} < {distance_threshold})').index.tolist()
    df.loc[resistant_idx, 'resistant_description'] += f'{tmp_col}, '
  
  # ================================ in-day support and resistant ======================
  df['prev_close'] = df['Close'].shift(1)
  col_to_drop.append('prev_close')
  for col in target_col:

    support_idx = df.query(f'Open > {col} and Low < {col} and Close > {col}').index
    df.loc[support_idx, 'support_description'] += f'{col}, '

    resistant_idx = df.query(f'Open < {col} and High > {col} and Close < {col}').index

    df.loc[resistant_idx, 'resistant_description'] += f'{col}, '

  df['support_description'] = df['support_description'].apply(lambda x: ', '.join(list(set(x[:-2].split(', ')))))
  df['resistant_description'] = df['resistant_description'].apply(lambda x: ', '.join(list(set(x[:-2].split(', ')))))

  df['support_score'] = df['support_description'].apply(lambda x: len(list(set([s for s in x.split(', ') if s != '']))))
  df['resistant_score'] = df['resistant_description'].apply(lambda x: -1 * len(list(set([s for s in x.split(', ') if s != '']))))

  # ================================ breakthorough =====================================
  for col in target_col:

    break_up_idx = df.query(f'candle_color == 1 and Open < {col} and Close > {col}').index # entity_diff > -0.5 and 
    df.loc[break_up_idx, 'break_up_description'] += f'{col}, '

    break_down_idx = df.query(f'candle_color == -1 and Open > {col} and Close < {col}').index # entity_diff > -0.5 and 
    df.loc[break_down_idx, 'break_down_description'] += f'{col}, '

  df['break_up_description'] = df['break_up_description'].apply(lambda x: ', '.join(list(set(x[:-2].split(', ')))))
  df['break_down_description'] = df['break_down_description'].apply(lambda x: ', '.join(list(set(x[:-2].split(', ')))))

  df['break_up_score'] = df['break_up_description'].apply(lambda x: len(list(set([s for s in x.split(', ') if s != '']))))
  df['break_down_score'] = df['break_down_description'].apply(lambda x: -1 * len(list(set([s for s in x.split(', ') if s != '']))))

  # drop unnecessary columns
  for col in col_to_drop:
    if col in df.columns:
      df.drop(col, axis=1, inplace=True)
  
  # ================================ supporter and resistanter =========================
  # add support/supporter, resistant/resistanter for the last row
  max_idx = df.index.max() 
  df['resistant'] = np.nan
  df['resistanter'] = ''
  df['support'] = np.nan
  df['supporter'] = ''
  if df.loc[max_idx, 'resistant_description'] > '':
    resistanter_candidates = df.loc[max_idx, 'resistant_description'].split(', ')
    resistanters = {}
    for r in resistanter_candidates:
      resistanters[r] = df.loc[max_idx, r]
    resistanter = min(resistanters, key=resistanters.get)
    df.loc[max_idx, 'resistanter'] = resistanter
    df.loc[max_idx, 'resistant'] = df.loc[max_idx, resistanter]

  if df.loc[max_idx, 'support_description'] > '':
    supporter_candidates = df.loc[max_idx, 'support_description'].split(', ')
    supporters = {}
    for s in supporter_candidates:
      supporters[s] = df.loc[max_idx, s]
    supporter = max(supporters, key=supporters.get)
    df.loc[max_idx, 'supporter'] = supporter
    df.loc[max_idx, 'support'] = df.loc[max_idx, supporter]

  # ================================ dynamic support and resistant =====================
  if 'support_resistant' in perspective:

    # focus on the last row only
    max_idx = df.index.max()
    
    # linear fit support/resistant
    linear_fit_support = df.loc[max_idx, 'linear_fit_support'] if 'linear' in perspective else np.nan
    linear_fit_resistant = df.loc[max_idx, 'linear_fit_resistant'] if 'linear' in perspective else np.nan

    # renko support/resistant
    renko_support = df.loc[max_idx, 'renko_support'] if 'renko' in perspective else np.nan
    renko_resistant = df.loc[max_idx, 'renko_resistant'] if 'renko' in perspective else np.nan
    
    # calculate support and resistant from renko, linear_fit and candle_gap
    support_candidates = {'linear': linear_fit_support, 'renko': renko_support}
    static_support = df.loc[max_idx, 'support_description'].split(', ')
    static_support = [x for x in static_support if x != '']
    for ss in static_support:
      support_candidates[ss] = df.loc[max_idx, ss]

    resistant_candidates = {'linear':linear_fit_resistant, 'renko': renko_resistant}
    static_resistant = df.loc[max_idx, 'resistant_description'].split(', ')
    static_resistant = [x for x in static_resistant if x != '']
    for sr in static_resistant:
      resistant_candidates[sr] = df.loc[max_idx, sr]

    # support
    supporter = ''
    support = np.nan  

    to_pop = []
    for k in support_candidates.keys():
      if np.isnan(support_candidates[k]):
        to_pop += [k]
    for k in to_pop:
      support_candidates.pop(k)

    if len(support_candidates) > 0:
      supporter = max(support_candidates, key=support_candidates.get)
      support = support_candidates[supporter]

    if supporter == 'linear':
      valid_idxs = df.query('linear_slope == linear_slope').index
    elif supporter == 'renko':
      valid_idxs = df[df.loc[max_idx, 'renko_start']:].index
    elif supporter != '':
      valid_idxs = df.index[-10:]
    else:
      valid_idxs = []
    df.loc[valid_idxs, 'support'] = support
    df.loc[valid_idxs, 'supporter'] = supporter

    # resistant
    resistanter = ''
    resistant = np.nan

    to_pop = []
    for k in resistant_candidates.keys():
      if np.isnan(resistant_candidates[k]):
        to_pop += [k]
    for k in to_pop:
      resistant_candidates.pop(k)

    if len(resistant_candidates) > 0:
      resistanter = min(resistant_candidates, key=resistant_candidates.get)
      resistant = resistant_candidates[resistanter]

    valid_idxs = []
    if resistanter == 'linear':
      valid_idxs = df.query('linear_slope == linear_slope').index
    elif resistanter == 'renko':
      valid_idxs = df[df.loc[max_idx, 'renko_start']:].index
    elif resistanter != '':
      valid_idxs = df.index[-10:]
    else:
      pass

    df.loc[valid_idxs, 'resistant'] = resistant
    df.loc[valid_idxs, 'resistanter'] = resistanter
  
  return df


# ================================================ Trend indicators ================================================= #
# ADX(Average Directional Index) 
def add_adx_features(df, n=14, ohlcv_col=default_ohlcv_col, fillna=False, adx_threshold=25):
  """
  Calculate ADX(Average Directional Index)

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param adx_threshold: the threshold to filter none-trending signals
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
  # col_to_drop = []

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  # close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

  # calculate true range
  df = add_atr_features(df=df, n=n, cal_signal=False)

  # difference of high/low between 2 continuouss days
  df['high_diff'] = df[high] - df[high].shift(1)
  df['low_diff'] = df[low].shift(1) - df[low]
  
  # plus/minus directional movements
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

  # (pdi-mdi) / (adx/25)
  df['adx_diff'] = (df['pdi'] - df['mdi'])# * (df['adx']/adx_threshold)
  df['adx_diff_ma'] = em(series=df['adx_diff'], periods=5).mean()

  # fill na values
  if fillna:
    for col in ['pdm', 'mdm', 'atr', 'pdi', 'mdi', 'dx', 'adx']:
      df[col] = df[col].replace([np.inf, -np.inf], np.nan).fillna(0)
  
  # drop redundant columns
  df.drop(['high_diff', 'low_diff', 'zero', 'pdm', 'mdm'], axis=1, inplace=True)

  return df

# Aroon
def add_aroon_features(df, n=25, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True, boundary=[50, 50]):
  """
  Calculate Aroon

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param boundary: upper and lower boundary for calculating signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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

  # calculate gap between aroon_up and aroon_down
  df['aroon_gap'] = (df['aroon_up'] - df['aroon_down'])

  return df

# CCI(Commidity Channel Indicator)
def add_cci_features(df, n=20, c=0.015, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True, boundary=[200, -200]):
  """
  Calculate CCI(Commidity Channel Indicator) 

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param c: constant value used in cci calculation
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param boundary: upper and lower boundary for calculating signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
  
  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

  # calculate cci
  pp = (df[high] + df[low] + df[close]) / 3.0
  mad = lambda x : np.mean(np.abs(x-np.mean(x)))
  cci = (pp - pp.rolling(n, min_periods=0).mean()) / (c * pp.rolling(n).apply(mad,True))

  # assign values to dataframe
  df['cci'] = cci

  # calculate siganl
  df['cci_ma'] = sm(series=df['cci'], periods=5).mean() #cal_moving_average(df=df, target_col='cci', ma_windows=[3, 5])

  return df

# DPO(Detrended Price Oscillator)
def add_dpo_features(df, n=20, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate DPO(Detrended Price Oscillator) 

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
  
  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
def add_ichimoku_features(df, n_short=9, n_medium=26, n_long=52, method='ta', is_shift=True, ohlcv_col=default_ohlcv_col, fillna=False, cal_status=True):
  """
  Calculate Ichimoku indicators

  :param df: original OHLCV dataframe
  :param n_short: short window size (9)
  :param n_medium: medium window size (26)
  :param n_long: long window size (52)
  :param method: original/ta way to calculate ichimoku indicators
  :param is_shift: whether to shift senkou_a and senkou_b n_medium units
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated


  # signal: 在tankan平移, kijun向下的时候应该卖出; 在tankan向上, kijun向上或平移的时候应该买入
  """
  # copy dataframe
  df = df.copy()
  col_to_drop = []

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

  # use original method to calculate ichimoku indicators
  if method == 'original':
    df = cal_moving_average(df=df, target_col=high, ma_windows=[n_short, n_medium, n_long], window_type='sm')
    df = cal_moving_average(df=df, target_col=low, ma_windows=[n_short, n_medium, n_long], window_type='sm')

    # generate column names
    short_high = f'{high}_ma_{n_short}'
    short_low = f'{low}_ma_{n_short}'
    medium_high = f'{high}_ma_{n_medium}'
    medium_low = f'{low}_ma_{n_medium}'
    long_high = f'{high}_ma_{n_long}'
    long_low = f'{low}_ma_{n_long}'
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

  # drop redundant columns  
  df.drop(col_to_drop, axis=1, inplace=True)

  return df

# KST(Know Sure Thing)
def add_kst_features(df, r1=10, r2=15, r3=20, r4=30, n1=10, n2=10, n3=10, n4=15, nsign=9, ohlcv_col=default_ohlcv_col, fillna=False):
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
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
  # col_to_drop = []

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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

  return df

# MACD(Moving Average Convergence Divergence)
def add_macd_features(df, n_fast=12, n_slow=26, n_sign=9, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate MACD(Moving Average Convergence Divergence)

  :param df: original OHLCV dataframe
  :param n_fast: ma window of fast ma
  :param n_slow: ma window of slow ma
  :paran n_sign: ma window of macd signal line
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
  
  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
def add_mi_features(df, n=9, n2=25, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate Mass Index

  :param df: original OHLCV dataframe
  :param n: ema window of high-low difference
  :param n_2: window of cumsum of ema ratio
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
  
  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  # close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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

    conditions = {
      'up': 'triger_signal == "b"', 
      'down': 'complete_signal == "s"'} 
    values = {
      'up': 'b', 
      'down': 's'}
    df = assign_condition_value(df=df, column='mi_signal', condition_dict=conditions, value_dict=values, default_value='n')

    df.drop(['benchmark', 'triger_signal', 'complete_signal'], axis=1, inplace=True)

  return df

# TRIX
def add_trix_features(df, n=15, n_sign=9, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True, signal_mode='mix'):
  """
  Calculate TRIX

  :param df: original OHLCV dataframe
  :param n: ema window of close price
  :param n_sign: ema window of signal line (ema of trix)
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
  
  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
  df['trix_diff'] = df['trix'] - df['trix_sign']

  return df

# Vortex
def add_vortex_features(df, n=14, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate Vortex indicator

  :param df: original OHLCV dataframe
  :param n: ema window of close price
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
  
  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
  df['vortex_diff'] = df['vortex_pos'] - df['vortex_neg']
  # df['vortex_diff'] = df['vortex_diff'] - df['vortex_diff'].shift(1)

  # calculate signal
  if cal_signal:
    df['vortex_signal'] = cal_crossover_signal(df=df, fast_line='vortex_pos', slow_line='vortex_neg')

  return df

# PSAR
def add_psar_features(df, ohlcv_col=default_ohlcv_col, step=0.02, max_step=0.10, fillna=False):
  """
  Calculate Parabolic Stop and Reverse (Parabolic SAR) indicator

  :param df: original OHLCV dataframe
  :param step: unit of a step
  :param max_step: up-limit of step
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
   
  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

  df['psar'] = df[close].copy()
  df['psar_up'] = np.NaN
  df['psar_down'] = np.NaN

  up_trend = True
  af = step
  idx = df.index.tolist()
  up_trend_high = df.loc[idx[0], high]
  down_trend_low = df.loc[idx[0], low]
  
  for i in range(2, len(df)):
    current_idx = idx[i]
    previous_idx = idx[i-1]
    previous_previous_idx = idx[i-2]

    reversal = False
    max_high = df.loc[current_idx, high]
    min_low = df.loc[current_idx, low]

    if up_trend:
      df.loc[current_idx, 'psar'] = df.loc[previous_idx, 'psar'] + (af * (up_trend_high - df.loc[previous_idx, 'psar']))

      if min_low < df.loc[current_idx, 'psar']:
        reversal = True
        df.loc[current_idx, 'psar'] = up_trend_high
        down_trend_low = min_low
        af = step
      else:
        if max_high > up_trend_high:
          up_trend_high = max_high
          af = min(af+step, max_step)

        l1 = df.loc[previous_idx, low]
        l2 = df.loc[previous_previous_idx, low]
        if l2 < df.loc[current_idx, 'psar']:
          df.loc[current_idx, 'psar'] = l2
        elif l1 < df.loc[current_idx, 'psar']:
          df.loc[current_idx, 'psar'] = l1

    else:
      df.loc[current_idx, 'psar'] = df.loc[previous_idx, 'psar'] - (af * (df.loc[previous_idx, 'psar'] - down_trend_low))

      if max_high > df.loc[current_idx, 'psar']:
        reversal = True
        df.loc[current_idx, 'psar'] = down_trend_low
        up_trend_high = max_high
        af = step
      else:
        if min_low < down_trend_low:
          down_trend_low = min_low
          af = min(af+step, max_step)

        h1 = df.loc[previous_idx, high]
        h2 = df.loc[previous_previous_idx, high]
        if h2 > df.loc[current_idx, 'psar']:
          df.loc[current_idx, 'psar'] = h2
        elif h1 > df.loc[current_idx, 'psar']:
          df.loc[current_idx, 'psar'] = h1

    up_trend = (up_trend != reversal)

    if up_trend:
      df.loc[current_idx, 'psar_up'] = df.loc[current_idx, 'psar']
    else:
      df.loc[current_idx, 'psar_down'] = df.loc[current_idx, 'psar']

  # fill na values
  if fillna:
    for col in ['psar', 'psar_up', 'psar_down']:
      df[col] = df[col].fillna(method='ffill').fillna(-1)

  return df

# Schaff Trend Cycle
def add_stc_features(df, n_fast=23, n_slow=50, n_cycle=10, n_smooth=3, ohlcv_col=default_ohlcv_col, fillna=False):
  """
  Calculate Schaff Trend Cycle indicator

  :param df: original OHLCV dataframe
  :param n_fast: short window
  :param n_slow: long window
  :param n_cycle: cycle size
  :param n_smooth: ema period over stoch_d and stock_kd
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()
   
  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

  # ema and macd
  ema_fast = em(series=df[close], periods=n_fast, fillna=fillna).mean()
  ema_slow = em(series=df[close], periods=n_slow, fillna=fillna).mean()
  macd = ema_fast - ema_slow
  macd_min = sm(series=macd, periods=n_cycle, fillna=fillna).min()
  macd_max = sm(series=macd, periods=n_cycle, fillna=fillna).max()

  stoch_k = 100 * (macd - macd_min) / (macd_max - macd_min)
  stoch_d = em(series=stoch_k, periods=n_smooth, fillna=fillna).mean()
  stoch_d_min = sm(series=stoch_d, periods=n_cycle).min()
  stoch_d_max = sm(series=stoch_d, periods=n_cycle).max()
  stoch_kd = 100 * (stoch_d - stoch_d_min) / (stoch_d_max - stoch_d_min)

  stc = em(series=stoch_kd, periods=n_smooth, fillna=fillna).mean()

  df['stc'] = stc
  df['25'] = 25
  df['75'] = 75
  df['stc_signal'] = cal_boundary_signal(df=df, upper_col='stc', upper_boundary='25', lower_col='stc', lower_boundary='75')
  
  df.drop(['25', '75'], axis=1, inplace=True)

  return df

# Renko
def add_renko_features(df, brick_size_factor=0.05, dynamic_brick=True, merge_duplicated=True):
  """
  Calculate Renko indicator
  :param df: original OHLCV dataframe
  :param brick_size_factor: if not using atr, brick size will be set to Close*brick_size_factor
  :param merge_duplicated: whether to merge duplicated indexes in the final result
  :param dynamic_brick: whether to use dynamic brick size
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """

  # reset index and copy df
  original_df = util.remove_duplicated_index(df=df, keep='last')
  df = original_df.copy()

  if dynamic_brick:
    # use dynamic brick size: brick_size_factor * Close price
    df['bsz'] = (df['Close'] * brick_size_factor).round(3)
  
  else:
    # use static brick size: brick_size_factor * Close price
    df['bsz'] = (df['Close'].values[0] * brick_size_factor).round(3)

  na_bsz = df.query('bsz != bsz').index 
  df = df.drop(index=na_bsz).reset_index()
  brick_size = df['bsz'].values[0]

  # construct renko_df, initialize values for first row
  columns = ['Date', 'Open', 'High', 'Low', 'Close']
  renko_df = pd.DataFrame(columns=columns, data=[], )
  renko_df.loc[0, columns] = df.loc[0, columns]
  close = df.loc[0, 'Close'] // brick_size * brick_size
  renko_df.loc[0, ['Open', 'High', 'Low', 'Close']] = [close-brick_size, close, close-brick_size, close]
  renko_df['uptrend'] = True
  renko_df['renko_brick_height'] = brick_size
  columns = ['Date', 'Open', 'High', 'Low', 'Close', 'uptrend', 'renko_brick_height']

  # go through the dataframe
  for index, row in df.iterrows():

    # get current date and close price
    date = row['Date']
    close = row['Close']
    
    # get previous trend and close price
    row_p1 = renko_df.iloc[-1]
    uptrend = row_p1['uptrend']
    close_p1 = row_p1['Close']
    brick_size_p1 = row_p1['renko_brick_height']

    # calculate bricks    
    bricks = int((close - close_p1) / brick_size)
    data = []
    
    # if in a uptrend and close_diff is larger than 1 brick
    if uptrend and bricks >=1 :
      for i in range(bricks):
        r = [date, close_p1, close_p1+brick_size, close_p1, close_p1+brick_size, uptrend, brick_size]
        data.append(r)
        close_p1 += brick_size
      brick_size = row['bsz']

    # if in a uptrend and closs_diff is less than -2 bricks
    elif uptrend and bricks <= -2:
      # flip trend
      uptrend = not uptrend
      bricks += 1
      close_p1 -= brick_size_p1

      for i in range(abs(bricks)):
        r = [date, close_p1, close_p1, close_p1-brick_size, close_p1-brick_size, uptrend, brick_size]
        data.append(r)
        close_p1 -= brick_size
      brick_size = row['bsz']

    # if in a downtrend and close_diff is less than -1 brick
    elif not uptrend and bricks <= -1:
      for i in range(abs(bricks)):
        r = [date, close_p1, close_p1, close_p1-brick_size, close_p1-brick_size, uptrend, brick_size]
        data.append(r)
        close_p1 -= brick_size
      brick_size = row['bsz']

    # if in a downtrend and close_diff is larger than 2 bricks
    elif not uptrend and bricks >= 2:
      # flip trend
      uptrend = not uptrend
      bricks -= 1
      close_p1 += brick_size_p1

      for i in range(abs(bricks)):
        r = [date, close_p1, close_p1+brick_size, close_p1, close_p1+brick_size, uptrend, brick_size]
        data.append(r)
        close_p1 += brick_size
      brick_size = row['bsz']

    else:
      continue
      
    # construct the [1:] rows and attach it to the first row
    tmp_row = pd.DataFrame(data=data, columns=columns)
    renko_df = pd.concat([renko_df, tmp_row], sort=False)

  # get back to original dataframe
  df = original_df

  # convert renko_df to time-series, add extra features(columns) to renko_df
  renko_df = util.df_2_timeseries(df=renko_df, time_col='Date')
  renko_df.rename(columns={'Open':'renko_o', 'High': 'renko_h', 'High': 'renko_h', 'Low': 'renko_l', 'Close':'renko_c', 'uptrend': 'renko_color'}, inplace=True)
  
  # renko brick start/end points
  renko_df['renko_start'] = renko_df.index.copy()
  renko_df['renko_end'] = renko_df['renko_start'].shift(-1).fillna(df.index.max())
  renko_df['renko_duration'] = renko_df['renko_end'] - renko_df['renko_start']
  renko_df['renko_duration'] = renko_df['renko_duration'].apply(lambda x: x.days+1).astype(float)
  renko_df['renko_duration_p1'] = renko_df['renko_duration'].shift(1)

  # renko color(green/red), trend(u/d), flip_point(renko_real), same-direction-accumulation(renko_brick_sda), sda-moving sum(renko_brick_ms), number of bricks(for later calculation)
  renko_df['renko_color'] = renko_df['renko_color'].replace({True: 'green', False:'red'})
  renko_df['renko_direction'] = renko_df['renko_color'].replace({'green':'u', 'red':'d'})
  renko_df['renko_real'] = renko_df['renko_color'].copy()
  renko_df['renko_brick_number'] = 1
  
  # merge rows with duplicated date (e.g. more than 1 brick in a single day)
  if merge_duplicated:
    
    # remove duplicated date index
    duplicated_idx = list(set(renko_df.index[renko_df.index.duplicated()]))
    for idx in duplicated_idx:
      tmp_rows = renko_df.loc[idx, ].copy()

      # make sure they are in same color
      colors = tmp_rows['renko_color'].unique()
      if len(colors) == 1:
        color = colors[0]
        if color == 'green':
          renko_df.loc[idx, 'renko_o'] = tmp_rows['renko_o'].min()
          renko_df.loc[idx, 'renko_l'] = tmp_rows['renko_l'].min()
          renko_df.loc[idx, 'renko_h'] = tmp_rows['renko_h'].max()
          renko_df.loc[idx, 'renko_c'] = tmp_rows['renko_c'].max()
          renko_df.loc[idx, 'renko_brick_height'] = tmp_rows['renko_brick_height'].sum()
          renko_df.loc[idx, 'renko_brick_number'] = tmp_rows['renko_brick_number'].sum()
        elif color == 'red':
          renko_df.loc[idx, 'renko_o'] = tmp_rows['renko_o'].max()
          renko_df.loc[idx, 'renko_l'] = tmp_rows['renko_l'].min()
          renko_df.loc[idx, 'renko_h'] = tmp_rows['renko_h'].max()
          renko_df.loc[idx, 'renko_c'] = tmp_rows['renko_c'].min()
          renko_df.loc[idx, 'renko_brick_height'] = tmp_rows['renko_brick_height'].sum()
          renko_df.loc[idx, 'renko_brick_number'] = tmp_rows['renko_brick_number'].sum() 
        else:
          print(f'unknown renko color {color}')
          continue 
      else:
        print('duplicated index with different renko colors!')
        continue
    renko_df = util.remove_duplicated_index(df=renko_df, keep='last')

  # calculate accumulated renko trend (so called "renko_series")
  series_len_short = 3
  series_len_long = 5
  renko_df['renko_series_short'] = 'n' * series_len_short
  renko_df['renko_series_long'] = 'n' * series_len_long
  prev_idx = None
  for idx, row in renko_df.iterrows():
    if prev_idx is not None:
      renko_df.loc[idx, 'renko_series_short'] = (renko_df.loc[prev_idx, 'renko_series_short'] + renko_df.loc[idx, 'renko_direction'])[-series_len_short:]
      renko_df.loc[idx, 'renko_series_long'] = (renko_df.loc[prev_idx, 'renko_series_long'] + renko_df.loc[idx, 'renko_direction'])[-series_len_long:]
    prev_idx = idx
  renko_df['renko_series_short_idx'] = renko_df['renko_series_short'].apply(lambda x: x.count('u') - x.count('d')).astype(int)
  renko_df['renko_series_long_idx'] = renko_df['renko_series_long'].apply(lambda x: x.count('u') - x.count('d')).astype(int)
    
  # drop currently-existed renko_df columns from df, merge renko_df into df 
  for col in df.columns:
    if 'renko' in col:
      df.drop(col, axis=1, inplace=True)
  df = pd.merge(df, renko_df, how='left', left_index=True, right_index=True)

  # for rows in downtrend, renko_brick_height = -renko_brick_height
  red_idx = df.query('renko_color == "red"').index
  df.loc[red_idx, 'renko_brick_height'] = -df.loc[red_idx, 'renko_brick_height']

  # fill na values
  renko_columns = ['renko_o', 'renko_h','renko_l', 'renko_c', 'renko_color', 'renko_brick_height', 'renko_brick_number','renko_start', 'renko_end', 'renko_duration', 'renko_duration_p1', 'renko_direction', 'renko_series_short', 'renko_series_long', 'renko_series_short_idx', 'renko_series_long_idx'] # , 'renko_direction', 'renko_series_short', 'renko_series_long'
  for col in renko_columns:
    df[col] = df[col].fillna(method='ffill')

  for col in ['renko_series_short_idx', 'renko_series_long_idx']:
    df[col] = df[col].fillna(0)

  # calculate length(number of days to the end of current brick) 
  # calculate of each brick(or merged brick): renko_brick_length, renko_countdown_days(for ploting)
  max_idx = df.index.max()
  if merge_duplicated:
    df['s']  = df.index
    if df['s'].max() == max_idx:
      max_idx = max_idx + datetime.timedelta(days=1)
    df['renko_countdown_days'] = df['renko_end'] - df['s'] 
    df['renko_brick_length'] = df['s'] - df['renko_start']
    df['renko_brick_length'] = df['renko_brick_length'].apply(lambda x: x.days+1).astype(float)
    df.drop('s', axis=1, inplace=True)
  else:
    df['renko_countdown_days'] = 1
    df['renko_brick_length'] = 1

  # below/among/above renko bricks  
  above_idx = df.query('Close > renko_h').index
  among_idx = df.query('renko_l <= Close <= renko_h').index
  below_idx = df.query('Close < renko_l').index
  df.loc[above_idx, 'renko_position'] = 1
  df.loc[among_idx, 'renko_position'] = 0
  df.loc[below_idx, 'renko_position'] = -1 

  # renko support and resistant
  df.loc[above_idx, 'renko_support'] = df.loc[above_idx, 'renko_h']
  df.loc[below_idx, 'renko_resistant'] = df.loc[below_idx, 'renko_l']
  df.loc[among_idx, 'renko_support'] = df.loc[among_idx, 'renko_l']
  df.loc[among_idx, 'renko_resistant'] = df.loc[among_idx, 'renko_h']

  return df


# ================================================ Volume indicators ================================================ #
# Accumulation Distribution Index
def add_adi_features(df, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate Accumulation Distribution Index

  :param df: original OHLCV dataframe
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """

  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  volume = ohlcv_col['volume']

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
def add_cmf_features(df, n=20, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate Chaikin Money FLow

  :param df: original OHLCV dataframe
  :param n: ema window of close price
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """

  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  volume = ohlcv_col['volume']

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
    df['cmf_signal'] = cal_boundary_signal(df=df, upper_col='cmf', lower_col='cmf', upper_boundary=0.05, lower_boundary=-0.05)

  return df

# Ease of movement (EoM, EMV)
def add_eom_features(df, n=20, ohlcv_col=default_ohlcv_col, fillna=False):
  """
  Calculate Vortex indicator

  :param df: original OHLCV dataframe
  :param n: ema window of close price
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """

  # copy dataframe
  df = df.copy()
  # col_to_drop = []

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  # close = ohlcv_col['close']
  volume = ohlcv_col['volume']

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

  return df

# Force Index (FI)
def add_fi_features(df, n1=2, n2=22, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate Force Index

  :param df: original OHLCV dataframe
  :param n: ema window of close price
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """

  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  volume = ohlcv_col['volume']

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
def add_nvi_features(df, n=255, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate Negative Volume Index (NVI)

  :param df: original OHLCV dataframe
  :param n: ema window of close price
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  volume = ohlcv_col['volume']

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
def add_obv_features(df, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate Force Index

  :param df: original OHLCV dataframe
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  volume = ohlcv_col['volume']

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

  df.drop('OBV', axis=1, inplace=True)
  return df

# *Volume-price trend (VPT)
def add_vpt_features(df, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate Vortex indicator

  :param df: original OHLCV dataframe
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  volume = ohlcv_col['volume']

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
def add_ao_features(df, n_short=5, n_long=34, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate Awesome Oscillator

  :param df: original OHLCV dataframe
  :param n_short: short window size for calculating sma
  :param n_long: long window size for calculating sma
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  # close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

  # calculate ao
  mp = 0.5 * (df[high] + df[low])
  ao = mp.rolling(n_short, min_periods=0).mean() - mp.rolling(n_long, min_periods=0).mean()

  # fill na values
  if fillna:
    ao = ao.replace([np.inf, -np.inf], np.nan).fillna(0)

  # assign ao to df
  df['ao'] = ao
  df['ao_ma'] = sm(series=df['ao'], periods=2).mean()

  return df

# Kaufman's Adaptive Moving Average (KAMA)
def cal_kama(df, n1=10, n2=2, n3=30, ohlcv_col=default_ohlcv_col, fillna=False):
  """
  Calculate Kaufman's Adaptive Moving Average

  :param df: original OHLCV dataframe
  :param n1: number of periods for Efficiency Ratio(ER)
  :param n2: number of periods for the fastest EMA constant
  :param n3: number of periods for the slowest EMA constant
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

  # calculate kama
  close_values = df[close].values
  vol = pd.Series(abs(df[close] - np.roll(df[close], 1)))

  ER_num = abs(close_values - np.roll(close_values, n1))
  ER_den = vol.rolling(n1).sum()
  ER = ER_num / ER_den
  ER = ER.fillna(method='ffill')

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
def add_kama_features(df, n_param={'kama_fast': [10, 2, 30], 'kama_slow': [10, 5, 30]}, ohlcv_col=default_ohlcv_col, fillna=False):
  """
  Calculate Kaufman's Adaptive Moving Average Signal

  :param df: original OHLCV dataframe
  :param n_param: series of n parameters fro calculating kama in different periods
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
      df = cal_kama(df=df, n1=n1, n2=n2, n3=n3, ohlcv_col=ohlcv_col)
      df.rename(columns={'kama': k}, inplace=True)
  
  return df

# Money Flow Index(MFI)
def add_mfi_features(df, n=14, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True, boundary=[20, 80]):
  """
  Calculate Money Flow Index Signal

  :param df: original OHLCV dataframe
  :param n: ma window size
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param boundary: boundaries for overbuy/oversell
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  volume = ohlcv_col['volume']

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
    df['mfi_signal'] = cal_boundary_signal(df=df, upper_col='mfi', lower_col='mfi', upper_boundary=max(boundary), lower_boundary=min(boundary))
    df = remove_redundant_signal(df=df, signal_col='mfi_signal', pos_signal='s', neg_signal='b', none_signal='n', keep='first')

  df.drop('up_or_down', axis=1, inplace=True)
  return df

# Relative Strength Index (RSI)
def add_rsi_features(df, n=14, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True, boundary=[30, 70]):
  """
  Calculate Relative Strength Index

  :param df: original OHLCV dataframe
  :param n: ma window size
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param boundary: boundaries for overbuy/oversell
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

  # calculate RSI
  diff = df[close].diff(1)#pct_change(1)
  
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
    df['rsi_signal'] = cal_boundary_signal(df=df, upper_col='rsi', lower_col='rsi', upper_boundary=max(boundary), lower_boundary=min(boundary), pos_signal='s', neg_signal='b', none_signal='n')
    df = remove_redundant_signal(df=df, signal_col='rsi_signal', pos_signal='s', neg_signal='b', none_signal='n', keep='first')

  return df

# Stochastic RSI
def add_srsi_features(df, n=14, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True, boundary=[20, 80]):
  """
  Calculate Stochastic RSI

  :param df: original OHLCV dataframe
  :param n: ma window size
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param boundary: boundaries for overbuy/oversell
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

  # calculate rsi
  df = add_rsi_features(df, n=n, ohlcv_col=ohlcv_col, cal_signal=False)
  
  # calculate stochastic
  rsi_min = df['rsi'].rolling(n, min_periods=0).min()
  rsi_max = df['rsi'].rolling(n, min_periods=0).max()
  stoch_rsi = (df['rsi'] - rsi_min) / (rsi_max - rsi_min)
  
  # fill na values, as 50 is the central line (rsi wave between 0-100)
  if fillna:
    stoch_rsi = stoch_rsi.replace([np.inf, -np.inf], np.nan).fillna(50)

  # assign stochastic values to df
  df['srsi'] = stoch_rsi

  # calculate signals
  if cal_signal:
    df['srsi_signal'] = cal_boundary_signal(df=df, upper_col='srsi', lower_col='srsi', upper_boundary=max(boundary), lower_boundary=min(boundary), pos_signal='s', neg_signal='b', none_signal='n')
    df = remove_redundant_signal(df=df, signal_col='srsi_signal', pos_signal='s', neg_signal='b', none_signal='n', keep='first')

  return df

# Stochastic Oscillator
def add_stoch_features(df, n=14, d_n=3, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True, boundary=[20, 80]):
  """
  Calculate Stochastic Oscillator

  :param df: original OHLCV dataframe
  :param n: ma window size
  :param d_n: ma window size for stoch
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param boundary: boundaries for overbuy/oversell
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
  df['stoch_diff'] = df['stoch_k'] - df['stoch_d']
  # df['stoch_diff'] = df['stoch_diff'] - df['stoch_diff'].shift(1)

  return df

# True strength index (TSI)
def add_tsi_features(df, r=25, s=13, ema_period=7, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate True strength index

  :param df: original OHLCV dataframe
  :param r: ma window size for high
  :param s: ma window size for low
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
def add_uo_features(df, s=7, m=14, l=28, ws=4.0, wm=2.0, wl=1.0, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=False):
  """
  Calculate Ultimate Oscillator

  :param df: original OHLCV dataframe
  :param s: short ma window size 
  :param m: mediem window size
  :param l: long window size
  :param ws: weight for short period
  :param wm: weight for medium period
  :param wl: weight for long period
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
  df['uo_diff'] = df['uo'] - df['uo'].shift(1)

  return df

# Williams %R
def add_wr_features(df, lbp=14, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True, boundary=[-20, -80]):
  """
  Calculate Williams %R

  :param df: original OHLCV dataframe
  :param lbp: look back period
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
    df['wr_signal'] = cal_boundary_signal(df=df, upper_col='wr', lower_col='wr', upper_boundary=max(boundary), lower_boundary=min(boundary))

  return df


# ================================================ Volatility indicators ============================================ #
# Average True Range
def add_atr_features(df, n=14, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate Average True Range

  :param df: original OHLCV dataframe
  :param n: ema window
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
    df['atr_diff'] = df['tr'] - df['atr']

  df.drop(['h_l', 'h_pc', 'l_pc'], axis=1, inplace=True)

  return df

# Mean Reversion
def add_mean_reversion_features(df, n=100, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True, mr_threshold=2):
  """
  Calculate Mean Reversion

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :param mr_threshold: the threshold to triger signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
  df['mr_price'] = f'{up_price}({up}%%),{down_price}({down}%%)'

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
def add_bb_features(df, n=20, ndev=2, ohlcv_col=default_ohlcv_col, fillna=False):
  """
  Calculate Bollinger Band

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param ndev: standard deviation factor
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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

  return df

# Donchian Channel
def add_dc_features(df, n=20, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=True):
  """
  Calculate Donchian Channel

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  # high = ohlcv_col['high']
  # low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
    conditions = {
      'up': f'{close} <= dc_low_band', 
      'down': f'{close} >= dc_high_band'} 
    values = {
      'up': 'b', 
      'down': 's'}
    df = assign_condition_value(df=df, column='dc_signal', condition_dict=conditions, value_dict=values, default_value='n')

  return df

# Keltner channel (KC)
def add_kc_features(df, n=10, ohlcv_col=default_ohlcv_col, method='atr', fillna=False, cal_signal=True):
  """
  Calculate Keltner channel (KC)

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param method: 'atr' or 'ta'
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

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
    conditions = {
      'up': f'{close} < kc_low_band', 
      'down': f'{close} > kc_high_band'} 
    values = {
      'up': 'b', 
      'down': 's'}
    df = assign_condition_value(df=df, column='kc_signal', condition_dict=conditions, value_dict=values, default_value='n')

  return df

# Ulcer Index
def add_ui_features(df, n=14, ohlcv_col=default_ohlcv_col, fillna=False, cal_signal=False):
  """
  Calculate Ulcer Index

  :param df: original OHLCV dataframe
  :param n: look back window size
  :param ohlcv_col: column name of Open/High/Low/Close/Volume
  :param fillna: whether to fill na with 0
  :param cal_signal: whether to calculate signal
  :returns: dataframe with new features generated
  """
  # copy dataframe
  df = df.copy()

  # set column names
  # open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  # volume = ohlcv_col['volume']

  # calculate UI
  recent_max_close = df[close].rolling(n, min_periods=0).max()
  pct_drawdown = ((df[close] - recent_max_close) / recent_max_close) * 100
  sqr_avg = (pct_drawdown ** 2).rolling(n).mean()
  ui = np.sqrt(sqr_avg)

  # fill na values
  if fillna:
    ui = ui.replace([np.inf, -np.inf], np.nan).fillna(method='backfill')

  # assign values to df
  df['ui'] = ui

  return df


# ================================================ Other indicators ================================================= #


# ================================================ Indicator visualization  ========================================= #
# plot bar
def plot_bar(df, target_col, start=None, end=None, width=0.8, alpha=1, color_mode='up_down', edge_color=(0,0,0,0.1), benchmark=None, add_line=False, title=None, use_ax=None, plot_args=default_plot_args):

  # copy dataframe within a specific period
  df = df[start:end].copy()

  # create figure
  ax = use_ax
  if ax is None:
    fig = mpf.figure(figsize=plot_args['figsize'])
    ax = fig.add_subplot(1,1,1, style='yahoo')

  # plot bar
  current = target_col
  previous = 'previous_' + target_col
  if color_mode == 'up_down':  
    df['color'] = 'red'  
    df[previous] = df[current].shift(1)
    df.loc[df[current] >= df[previous], 'color'] = 'green'

  # plot in benchmark mode
  elif color_mode == 'benchmark' and benchmark is not None:
    df['color'] = 'red'
    df.loc[df[current] > benchmark, 'color'] = 'green'

  # plot indicator
  if 'color' in df.columns:
    ax.bar(df.index, height=df[target_col], color=df.color, width=width , alpha=alpha, label=target_col, edgecolor=edge_color)

  if add_line:
    ax.plot(df[target_col], color=df.color, alpha=alpha, label=target_col)

  # title and legend
  ax.legend(bbox_to_anchor=plot_args['bbox_to_anchor'], loc=plot_args['loc'], ncol=plot_args['ncol'], borderaxespad=plot_args['borderaxespad']) 
  ax.set_title(title, rotation=plot_args['title_rotation'], x=plot_args['title_x'], y=plot_args['title_y'])
  ax.grid(True, axis='both', linestyle='-', linewidth=0.5, alpha=0.3)

  ax.yaxis.set_ticks_position(default_plot_args['yaxis_position'])

  # return ax
  if use_ax is not None:
    return ax

# plot volume
def plot_scatter(df, target_col, start=None, end=None, marker='.', alpha=1, color_mode='up_down', benchmark=None, add_line=False, title=None, use_ax=None, plot_args=default_plot_args):

  # copy dataframe within a specific period
  df = df[start:end].copy()

  # create figure
  ax = use_ax
  if ax is None:
    fig = mpf.figure(figsize=plot_args['figsize'])
    ax = fig.add_subplot(1,1,1, style='yahoo')

  # plot bar
  current = target_col
  previous = 'previous_' + target_col
  if color_mode == 'up_down':  
    df['color'] = 'red'  
    df[previous] = df[current].shift(1)
    df.loc[df[current] >= df[previous], 'color'] = 'green'

  # plot in benchmark mode
  elif color_mode == 'benchmark' and benchmark is not None:
    df['color'] = 'red'
    df.loc[df[current] > benchmark, 'color'] = 'green'

  # plot indicator
  if 'color' in df.columns:
    # df = cal_change_rate(df=df, target_col='Volume', add_accumulation=False, add_prefix=True)
    # threshold = 0.2
    # strong_trend_idx = df.query(f'Volume_rate >= {threshold} or Volume_rate <= {-threshold}').index
    # weak_trend_idx = df.query(f'{-threshold} < Volume_rate < {threshold}').index
    # ax.scatter(strong_trend_idx, df.loc[strong_trend_idx, 'Volume'], color=df.loc[strong_trend_idx, 'color'], label=target_col, alpha=0.4, marker='s')
    # ax.scatter(weak_trend_idx, df.loc[weak_trend_idx, 'adx'], color=df.loc[weak_trend_idx, 'color'], alpha=0.4, marker='_')
    ax.scatter(df.index, df[target_col], marker=marker,color=df.color, alpha=alpha, label=target_col)

  if add_line:
    ax.plot(df.index, df[target_col], color='black', linestyle='--', marker='.', alpha=alpha)

  # title and legend
  ax.legend(bbox_to_anchor=plot_args['bbox_to_anchor'], loc=plot_args['loc'], ncol=plot_args['ncol'], borderaxespad=plot_args['borderaxespad']) 
  ax.set_title(title, rotation=plot_args['title_rotation'], x=plot_args['title_x'], y=plot_args['title_y'])
  # ax.grid(True, axis='both', linestyle='-', linewidth=0.5, alpha=0.3)

  ax.yaxis.set_ticks_position(default_plot_args['yaxis_position'])

  # return ax
  if use_ax is not None:
    return ax

# plot trend index
def plot_up_down(df, col='trend_idx', start=None, end=None, use_ax=None, title=None, plot_args=default_plot_args):
  """
  Plot indicators around a benchmark

  :param df: dataframe which contains target columns
  :param start: start row to plot
  :param end: end row to stop
  :param use_ax: the already-created ax to draw on
  :param title: plot title
  :returns: figure with indicators and close price plotted
  :raises: none
  """
  # select data
  df = df[start:end].copy() 
  
  # calculate score moving average
  df[f'up_{col}_ma'] = em(series=df[f'up_{col}'], periods=3).mean()
  df[f'down_{col}_ma'] = em(series=df[f'down_{col}'], periods=3).mean()
  df[f'{col}_ma'] = em(series=df[f'{col}'], periods=3).mean()

  # change of score ma
  df[f'up_{col}_ma_change'] = df[f'up_{col}_ma'] - df[f'up_{col}_ma'].shift(1)
  df[f'down_{col}_ma_change'] = df[f'down_{col}_ma'] - df[f'down_{col}_ma'].shift(1)
  df[f'{col}_ma_change'] = df[f'{col}_ma'] - df[f'{col}_ma'].shift(1)
  # conditions = {
  #   'up': f'((up_{col}_ma_change > 0) and (down_{col}_ma_change > 0) and ({col} > 0))', 
  #   'down': f'((up_{col}_ma_change < 0) and (down_{col}_ma_change < 0)) or ({col}_ma_change < -0.5)'} 
  # values = {
  #   'up': 'u', 
  #   'down': 'd'}
  # df = assign_condition_value(df=df, column='{col}_trend', condition_dict=conditions, value_dict=values, default_value=np.nan)
  # df['{col}_trend'] = df['{col}_trend'].fillna(method='ffill')

  # create figure
  ax = use_ax
  if ax is None:
    fig = mpf.figure(figsize=plot_args['figsize'])
    ax = fig.add_subplot(1,1,1, style='yahoo')
  alpha = 0.4

  # plot benchmark(0)
  df['zero'] = 0
  ax.plot(df.index, df['zero'], color='grey', alpha=0.5*alpha)
  # # plot up_trend and down_trend
  # ax.fill_between(df.index, df.up_trend_idx_ma, df.zero, facecolor='green', interpolate=False, alpha=0.3, label='trend up') 
  # ax.fill_between(df.index, df.down_trend_idx_ma, df.zero, facecolor='red', interpolate=False, alpha=0.3, label='trend down')

  # # plot trend
  # df['prev_ta_trend'] = df['ta_trend'].shift(1)
  # green_mask = ((df.ta_trend == 'u') | (df.prev_ta_trend == 'u'))
  # red_mask = ((df.ta_trend == 'd') | (df.prev_ta_trend == 'd'))
  # ax.fill_between(df.index, df.up_trend_idx_ma, df.down_trend_idx_ma, where=green_mask,  facecolor='green', interpolate=False, alpha=0.3, label='trend up') 
  # ax.fill_between(df.index, df.up_trend_idx_ma, df.down_trend_idx_ma, where=red_mask, facecolor='red', interpolate=False, alpha=0.3, label='trend down')

  threshold = 0.5
  for direction in ['up', 'down']:
    
    direction_change_col = f'{direction}_{col}_ma_change'
    target_col = f'{direction}_{col}_direction'
    plot_col = f'{direction}_{col}_ma'
    
    conditions = {
      'up': f'{direction_change_col} > {threshold}' + (f' and {col} > 0' if direction == 'down' else ''), 
      'down': f'{direction_change_col} < {-threshold}' + (f' and down_{col} < 0' if direction == 'up' else '')} 
    values = {
      'up': 'u', 
      'down': 'd'}
    df = assign_condition_value(df=df, column=target_col, condition_dict=conditions, value_dict=values, default_value=np.nan)
    df[target_col] = df[target_col].fillna(method='ffill')
    green_mask = ((df[target_col] == "u") | (df[target_col].shift(1) == "u"))
    red_mask = ((df[target_col] == "d") | (df[target_col].shift(1) == "d"))
    ax.fill_between(df.index, df[plot_col], df.zero, where=green_mask,  facecolor='green', interpolate=False, alpha=0.3) 
    ax.fill_between(df.index, df[plot_col], df.zero, where=red_mask, facecolor='red', interpolate=False, alpha=0.15)
  
  # ichimoku_distance_day
  max_idx = df.index.max()
  x_signal = max_idx + datetime.timedelta(days=2)
  y_signal = 0
  text_signal = int(df.loc[max_idx, 'ichimoku_distance_day'])
  text_color = 'red' if text_signal < 0 else 'green'
  plt.annotate(f'ich: {text_signal}', xy=(x_signal, y_signal), xytext=(x_signal, y_signal), fontsize=12, xycoords='data', textcoords='data', color='black', va='center',  ha='left', bbox=dict(boxstyle="round", facecolor=text_color, alpha=0.05))

  # title and legend
  # ax.legend(bbox_to_anchor=plot_args['bbox_to_anchor'], loc=plot_args['loc'], ncol=plot_args['ncol'], borderaxespad=plot_args['borderaxespad']) 
  # ax.set_title(title, rotation=plot_args['title_rotation'], x=plot_args['title_x'], y=plot_args['title_y'])
  ax.grid(True, axis='y', linestyle='--', linewidth=0.5, alpha=0.3)
  ax.yaxis.set_ticks_position(default_plot_args['yaxis_position'])

  # return ax
  if use_ax is not None:
    return ax

# plot score and trigger score
def plot_score(df, start=None, end=None, width=0.8, use_ax=None, title=None, plot_args=default_plot_args):
  """
  Plot overall score and trigger score

  :param df: dataframe which contains target columns
  :param start: start row to plot
  :param end: end row to stop
  :param use_ax: the already-created ax to draw on
  :param title: plot title
  :returns: figure with indicators and close price plotted
  :raises: none
  """

  # select data
  df = df[start:end].copy() 

  # create figure
  ax = use_ax
  if ax is None:
    fig = mpf.figure(figsize=plot_args['figsize'])
    ax = fig.add_subplot(1,1,1, style='yahoo')
  alpha = 0.4

  # plot benchmark(0)
  df['zero'] = 0
  ax.plot(df.index, df['zero'], color='grey', alpha=0.5*alpha)

  # plot score
  df['prev_score'] = df['score'].shift(1)
  green_mask = ((df.score > 0) | (df.prev_score > 0))
  red_mask = ((df.score < 0) | (df.prev_score < 0))
  ax.fill_between(df.index, df.score, df.zero, where=green_mask,  facecolor='green', interpolate=False, alpha=0.2, label='trend up') 
  ax.fill_between(df.index, df.score, df.zero, where=red_mask, facecolor='red', interpolate=False, alpha=0.2, label='trend down')

  # plot trigger_score
  up_idx = df.query(f'trigger_score > 0').index
  down_idx = df.query(f'trigger_score < 0').index
  df['trigger_score_color'] = 'white'
  df.loc[up_idx, 'trigger_score_color'] = 'green'
  df.loc[down_idx, 'trigger_score_color'] = 'red'
  # ax.scatter(up_idx, df.loc[up_idx, 'trigger_score'], color='green', alpha=1, marker='_')
  # ax.scatter(down_idx, df.loc[down_idx, 'trigger_score'], color='red', alpha=1, marker='_')
  ax.bar(df.index, height=df['trigger_score'], color=df['trigger_score_color'], width=width, alpha=0.8)

  # title and legend
  ax.legend(bbox_to_anchor=plot_args['bbox_to_anchor'], loc=plot_args['loc'], ncol=plot_args['ncol'], borderaxespad=plot_args['borderaxespad']) 
  ax.set_title(title, rotation=plot_args['title_rotation'], x=plot_args['title_x'], y=plot_args['title_y'])
  # ax.grid(True, axis='y', linestyle='--', linewidth=0.5, alpha=0.3)
  ax.yaxis.set_ticks_position(default_plot_args['yaxis_position'])

  # return ax
  if use_ax is not None:
    return ax

# plot signals on price line
def plot_signal(df, start=None, end=None, signal_x='signal', signal_y='Close', use_ax=None, title=None, trend_val=default_trend_val, signal_val=default_signal_val, plot_args=default_plot_args):
  """
  Plot signals along with the price

  :param df: dataframe with price and signal columns
  :param start: start row to plot
  :param end: end row to stop
  :param signal_x: columnname of the signal x values (default 'signal')
  :param signal_y: columnname of the signal y values (default 'Close')
  :param use_ax: the already-created ax to draw on
  :param title: plot title
  :param trend_val: value of different kind of trends (e.g. 'u'/'d'/'n')
  :param signal_val: value of different kind of signals (e.g. 'b'/'s'/'n')
  :param plot_args: other plot arguments
  :returns: a signal plotted price chart
  :raises: none
  """
  # copy dataframe within the specific period
  df = df[start:end].copy()
  
  # use existed figure or create figure
  ax = use_ax
  if ax is None:
    fig = mpf.figure(figsize=plot_args['figsize'])
    ax = fig.add_subplot(1,1,1, style='yahoo')

  # plot settings
  settings = {
    'main': {'pos_signal_marker': 's', 'neg_signal_marker': 's', 'pos_trend_marker': 's', 'neg_trend_marker': 's', 'wave_trend_marker': '_', 'signal_alpha': 0.8, 'trend_alpha': 0.5, 'pos_color':'green', 'neg_color':'red', 'wave_color':'orange'},
    'other': {'pos_signal_marker': '^', 'neg_signal_marker': 'v', 'pos_trend_marker': '2', 'neg_trend_marker': '1', 'wave_trend_marker': '_', 'signal_alpha': 0.5, 'trend_alpha': 0.3, 'pos_color':'green', 'neg_color':'red', 'wave_color':'orange'}}
  style = settings['main'] if signal_x in ['signal'] else settings['other']

  # plot signal base line
  ax.plot(df.index, df[signal_y], label=signal_y, alpha=0)

  # plot trend
  trend_col = signal_x.replace('signal', 'trend')
  day_col = signal_x.replace('signal', 'day')
  if trend_col in df.columns:
    if signal_x not in ['inday_signal', 'short_signal', 'middle_signal', 'long_signal', 'signal']:
      for i in ['pos', 'neg', 'wave']:
        tmp_trend_value = trend_val[f'{i}_trend']
        tmp_data = df.query(f'{trend_col} == "{tmp_trend_value}"')
        ax.scatter(tmp_data.index, tmp_data[signal_y], marker=style[f'{i}_trend_marker'], color=style[f'{i}_color'], alpha=style['trend_alpha'])
    
    elif signal_x in ['inday_signal', 'short_signal', 'middle_signal', 'long_signal', 'signal']:
      score_col = signal_x.replace('signal', 'trend_score')
      # alpha_factor = 0.8 if signal_x == 'signal' else 0.6

      tmp_alpha = normalize(df[score_col].abs()) # * alpha_factor
      
      tmp_up = df.query(f'{score_col} > 0')
      tmp_down = df.query(f'{score_col} < 0')

      pos_marker = 's' if signal_x == 'signal' else 'x'
      neg_marker = 's' if signal_x == 'signal' else 'x'

      if len(tmp_up) > 0:
        facecolor = 'green'
        alpha = tmp_alpha.loc[tmp_up.index] 
        ax.scatter(tmp_up.index, tmp_up[signal_y], marker=pos_marker, color=facecolor, alpha=alpha)
      
      if len(tmp_down) > 0:
        facecolor ='red'
        alpha = tmp_alpha.loc[tmp_down.index] 
        ax.scatter(tmp_down.index, tmp_down[signal_y], marker=neg_marker, color=facecolor, alpha=alpha)

  # annotate number of days since signal triggered
  annotate_signal_day = True
  max_idx = df.index.max()
  ys = {'long_signal': 0, 'middle_signal': 2.75, 'short_signal': 5.5}
  if signal_x in ys.keys() and day_col in df.columns and annotate_signal_day:

    x_signal = max_idx + datetime.timedelta(days=3)
    y_signal = ys[signal_x]
    text_day = int(df.loc[max_idx, day_col])
    text_color = 'red' if text_day < 0 else 'green'
    plt.annotate(f'{signal_x.replace("_signal", "")}:{text_day} ', xy=(x_signal, y_signal), xytext=(x_signal, y_signal), fontsize=12, xycoords='data', textcoords='data', color='black', va='center',  ha='left', bbox=dict(boxstyle="round", facecolor=text_color, edgecolor='none', alpha=0.1))

  # overbuy and oversell
  if signal_x == 'os':

    # trigger_score
    tmp_data = df.query(f'(trigger_score > 0)')
    tmp_alpha = normalize(tmp_data['trigger_score'].abs())
    ax.scatter(tmp_data.index, tmp_data[signal_y], marker='|', color='green', alpha=tmp_alpha)

    # plot potential
    tmp_data = df.query(f'potential == "potential"')
    tmp_alpha = normalize(tmp_data['potential_score'].abs())
    ax.scatter(tmp_data.index, tmp_data[signal_y], marker='_', color='green', alpha=0.5)

    tmp_data = df.query(f'(bb_day == 1)')
    ax.scatter(tmp_data.index, tmp_data[signal_y], marker='.', color='orange', alpha=0.5) # color='none', edge

  if signal_x == 'ob':

    # trigger_score
    tmp_data = df.query(f'(trigger_score < 0)')
    tmp_alpha = normalize(tmp_data['trigger_score'].abs())
    ax.scatter(tmp_data.index, tmp_data[signal_y], marker='|', color='red', alpha=tmp_alpha)

    tmp_data = df.query(f'(bb_day == -1)')
    ax.scatter(tmp_data.index, tmp_data[signal_y], marker='.', color='orange', alpha=0.5)

  # buy and sell
  if signal_x == ' ':
    buy_data = df.query('signal == "b"')
    ax.scatter(buy_data.index, buy_data[signal_y], marker='^', color='green', alpha=0.5)

    sell_data = df.query('signal == "s"')
    ax.scatter(sell_data.index, sell_data[signal_y], marker='v', color='red', alpha=0.5)

  # plot renko
  # if False: # signal_x == 'b':

  #   idxs = df.index.tolist()
  #   min_idx = df.index.min()
  #   max_idx = df.index.max()
  #   signal_y_value = df[signal_y].values.max()

  #   # plot renko blocks
  #   if 'renko' in default_perspectives: 
  #     df.loc[min_idx, 'renko_real'] = df.loc[min_idx, 'renko_color']
  #     df.loc[max_idx, 'renko_real'] = df.loc[max_idx, 'renko_color']
  #     renko_real_idxs = df.query('renko_real == renko_real').index
  #     for i in range(1, len(renko_real_idxs)):
  #       start = renko_real_idxs[i-1]
  #       end = renko_real_idxs[i]
  #       end = idxs[idxs.index(end) - 1]
  #       renko_color = df.loc[start, 'renko_color']
  #       hatch = None #'/' if renko_color == 'green' else '\\' # 
  #       ax.fill_between(df[start:end].index, signal_y_value-0.75, signal_y_value+0.75, hatch=hatch, linewidth=1, edgecolor=renko_color, facecolor='None', alpha=0.5)
  #       ax.fill_between(df[start:end].index, signal_y_value-0.75, signal_y_value+0.75, hatch=hatch, linewidth=1, facecolor=renko_color, alpha=0.1)

  #     # renko_day
  #     x_signal = max_idx + datetime.timedelta(days=2)
  #     y_signal = signal_y_value
  #     text_signal = int(df.loc[max_idx, 'renko_duration'])
  #     text_color = df.loc[max_idx, 'renko_color'] # fontsize=14, 
  #     plt.annotate(f'{df.loc[max_idx, "renko_series_short"]}: {text_signal}', xy=(x_signal, y_signal), xytext=(x_signal, y_signal), fontsize=12, xycoords='data', textcoords='data', color='black', va='center',  ha='left', bbox=dict(boxstyle="round", facecolor=text_color, alpha=0.1))

  # plot signal
  # if signal_x in df.columns:
  #   if signal_x == 'signal':
  #     pass
  #   else:
  #     for i in ['pos', 'neg']:
  #       tmp_signal_value = signal_val[f'{i}_signal']
  #       tmp_data = df.query(f'{signal_x} == "{tmp_signal_value}"')
  #       ax.scatter(tmp_data.index, tmp_data[signal_y], marker=style[f'{i}_signal_marker'], color='none', edgecolor=style[f'{i}_color'], alpha=style['signal_alpha'])

  # legend and title
  ax.legend(loc='upper left')  
  
  ax.set_title(title, rotation=plot_args['title_rotation'], x=plot_args['title_x'], y=plot_args['title_y'])
  ax.grid(True, axis='x', linestyle='-', linewidth=0.5, alpha=0.1)
  ax.yaxis.set_ticks_position(default_plot_args['yaxis_position'])

  # return ax
  if use_ax is not None:
    return ax

# plot adx chart
def plot_adx(df, start=None, end=None, use_ax=None, title=None, plot_args=default_plot_args):
  """
  Plot adx chart

  :param df: dataframe with ichimoku indicator columns
  :param start: start row to plot
  :param end: end row to plot
  :param date_col: column name of Date
  :param use_ax: the already-created ax to draw on
  :param title: plot title
  :param plot_args: other plot arguments
  :returns: ichimoku plot
  :raises: none
  """
  # copy dataframe within a specific period
  df = df[start:end].copy()
  
  # create figure
  ax = use_ax
  if ax is None:
    fig = mpf.figure(figsize=plot_args['figsize'])
    ax = fig.add_subplot(1,1,1, style='yahoo')

  # idxs = df.index.tolist()
  # min_idx = df.index.min()
  # max_idx = df.index.max()

  # # plot renko blocks
  # if 'renko' in default_perspectives: 
  #   df.loc[min_idx, 'renko_real'] = df.loc[min_idx, 'renko_color']
  #   df.loc[max_idx, 'renko_real'] = df.loc[max_idx, 'renko_color']
  #   renko_real_idxs = df.query('renko_real == renko_real').index
  #   for i in range(1, len(renko_real_idxs)):
  #     start = renko_real_idxs[i-1]
  #     end = renko_real_idxs[i]
  #     end = idxs[idxs.index(end) - 1]
  #     renko_color = df.loc[start, 'renko_color']
  #     hatch = None #'/' if renko_color == 'green' else '\\' # 
  #     ax.fill_between(df[start:end].index, 10, -10, hatch=hatch, linewidth=1, edgecolor=renko_color, facecolor='None', alpha=1)
  #     ax.fill_between(df[start:end].index, 10, -10, hatch=hatch, linewidth=1, facecolor=renko_color, alpha=0.1)

  #   # renko_day
  #   x_signal = max_idx + datetime.timedelta(days=2)
  #   y_signal = 0
  #   text_signal = int(df.loc[max_idx, 'renko_duration'])
  #   text_color = df.loc[max_idx, 'renko_color'] # fontsize=14, 
  #   plt.annotate(f'{df.loc[max_idx, "renko_series_short"]}: {text_signal}', xy=(x_signal, y_signal), xytext=(x_signal, y_signal), fontsize=12, xycoords='data', textcoords='data', color='black', va='center',  ha='left', bbox=dict(boxstyle="round", facecolor=text_color, alpha=0.25))
  # else:
  #   ax.fill_between(df.index, 10, -10, hatch=None, linewidth=1, edgecolor='black', facecolor='grey', alpha=0.1)
  ax.fill_between(df.index, 10, -10, hatch=None, linewidth=1, facecolor='grey', edgecolor='black', alpha=0.1, zorder=0)

  # plot adx_diff_ma and adx_direction
  df['zero'] = 0
  ax.plot(df.index, df.zero, color='black', alpha=0.25, zorder=0)

  # df['adx_ma_diff'] = df['adx_value'] - df['adx_value_ma']
  # df['prev_adx_day'] = df['adx_day'].shift(1)
  # df['next_adx_day'] = df['adx_day'].shift(-1)
  # df['prev_adx_trend'] = df['adx_trend'].shift(1)
  # df['next_adx_trend'] = df['adx_trend'].shift(-1)
  # df['prev_adx_value_change'] = df['adx_value_change'].shift(1)
  # df['next_adx_value_change'] = df['adx_value_change'].shift(-1)
  # green_mask = ((df.adx_value_change > 0))# | (df.prev_adx_day > 0)) 
  # red_mask = ((df.adx_value_change < 0))# | (df.prev_adx_day < 0)) 
  # yellow_mask = ((df.adx_value_change == 0)) | ((df.adx_value_change > 0) & (df.prev_adx_value_change < 0)) | ((df.adx_value_change > 0) & (df.next_adx_value_change < 0)) | ((df.adx_value_change < 0) & (df.prev_adx_value_change > 0)) | ((df.adx_value_change < 0) & (df.next_adx_value_change > 0)) 
  # ax.fill_between(df.index, df.adx_diff_ma, df.zero, where=green_mask,  facecolor='green', interpolate=False, alpha=0.3, label='adx up') 
  # ax.fill_between(df.index, df.adx_diff_ma, df.zero, where=red_mask, facecolor='red', interpolate=False, alpha=0.3, label='adx down')
  # ax.fill_between(df.index, df.adx_diff_ma, df.zero, where=yellow_mask, facecolor='yellow', interpolate=False, alpha=0.3, label='adx switch')

  # green_mask = ((df.adx_value > df.adx_value_ma)) # | (df.prev_adx_day > 0)) 
  # red_mask = ((df.adx_value < df.adx_value_ma))# | (df.prev_adx_day < 0)) 
  # ax.fill_between(df.index, df.adx_value, df.adx_value_ma, where=green_mask,  facecolor='green', interpolate=False, alpha=0.6) 
  # ax.fill_between(df.index, df.adx_value, df.adx_value_ma, where=red_mask, facecolor='red', interpolate=False, alpha=0.6)
  
  target_col = 'adx_diff_ma'
  # gredn_df = df.loc[green_mask, ]
  # red_df = df.loc[red_mask]
  # ax.bar(gredn_df.index, height=gredn_df[target_col], color='green', edge_color=(0,0,0,1), width=datetime.timedelta(days=1), alpha=0.4, label=f'+{target_col}')
  # ax.bar(red_df.index, height=red_df[target_col], color='red', edge_color=(0,0,0,1), width=datetime.timedelta(days=1), alpha=0.4, label=f'-{target_col}')

  # df['adx_value'] = df['adx_value'] * (df['adx'] / 25)
  plot_bar(df=df, target_col=target_col, alpha=0.4, width=datetime.timedelta(days=1), color_mode='up_down', edge_color=(1,1,1,0), benchmark=0, title='', use_ax=ax, plot_args=default_plot_args)
  # 0.8
  # plot adx with 
  # color: green(uptrending), red(downtrending), orange(waving); 
  # marker: _(weak trend), s( strong trend)
  adx_threshold = 25

  # overlap_mask = green_mask & red_mask
  df['adx_color'] = 'orange'
  df.loc[df.adx_power_day > 0, 'adx_color'] = 'green'
  df.loc[df.adx_power_day < 0, 'adx_color'] = 'red'

  strong_trend_idx = df.query(f'adx >= {adx_threshold}').index
  weak_trend_idx = df.query(f'adx < {adx_threshold}').index
  ax.scatter(strong_trend_idx, df.loc[strong_trend_idx, 'adx'], color=df.loc[strong_trend_idx, 'adx_color'], label='adx strong', alpha=0.4, marker='s', zorder=3)
  ax.scatter(weak_trend_idx, df.loc[weak_trend_idx, 'adx'], color=df.loc[weak_trend_idx, 'adx_color'], label='adx weak', alpha=0.4, marker='_', zorder=3)

  # plot moving average value of adx_value
  ax.plot(df.index, df.adx_value_prediction, color='black', linestyle='-', alpha=0.5, zorder=3)

  # title and legend
  ax.legend(bbox_to_anchor=plot_args['bbox_to_anchor'], loc=plot_args['loc'], ncol=plot_args['ncol'], borderaxespad=plot_args['borderaxespad']) 
  ax.set_title(title, rotation=plot_args['title_rotation'], x=plot_args['title_x'], y=plot_args['title_y'])
  ax.yaxis.set_ticks_position(default_plot_args['yaxis_position'])

  # return ax
  if use_ax is not None:
    return ax

# plot candlestick chart
def plot_candlestick(df, start=None, end=None, date_col='Date', add_on=['split', 'gap', 'support_resistant', 'pattern'], use_ax=None, ohlcv_col=default_ohlcv_col, color=default_candlestick_color, plot_args=default_plot_args, interval='day'):
  """
  Plot candlestick chart

  :param df: dataframe with price and signal columns
  :param start: start row to plot
  :param end: end row to stop
  :param date_col: columnname of the date values
  :param add_on: add ons beyond basic candlesticks
  :param width: width of candlestick
  :param use_ax: the already-created ax to draw on
  :param ohlcv_col: columns names of Open/High/Low/Close/Volume
  :param color: up/down color of candlestick
  :param plot_args: other plot arguments
  :param interval: interval of the sec_data(day/week/month/year)
  :returns: a candlestick chart
  :raises: none
  """
  # copy dataframe within a specific period
  df = df[start:end].copy()

  # create figure
  ax = use_ax
  if ax is None:
    fig = mpf.figure(figsize=plot_args['figsize'])
    ax = fig.add_subplot(1,1,1, style='yahoo')
  
  # set column names
  open = ohlcv_col['open']
  high = ohlcv_col['high']
  low = ohlcv_col['low']
  close = ohlcv_col['close']
  
  # get indexes and max index
  idxs = df.index.tolist()
  max_idx = idxs[-1]
  min_idx = df.index.min()
  max_x = max_idx + datetime.timedelta(days=5)
  padding = (df.High.max() - df.Low.min()) / 100

  # annotate split
  if 'split' in add_on and 'Split' in df.columns:
    
    splited = df.query('Split != 1.0').index
    all_idx = df.index.tolist()
    for s in splited:
      x = s
      y = df.loc[s, 'High']
      x_text = all_idx[max(0, all_idx.index(s)-2)]
      y_text = y + df.High.max()*0.1
      sp = round(df.loc[s, 'Split'], 4)
      plt.annotate(f'splited {sp}', xy=(x, y), xytext=(x_text,y_text), xycoords='data', textcoords='data', arrowprops=dict(arrowstyle='->', alpha=0.5), bbox=dict(boxstyle="round", fc="1.0", alpha=0.5))
  
  # annotate gaps
  if 'gap' in add_on:

    # for gap which start before 'start_date'
    if df.loc[min_idx, 'candle_gap_top'] > df.loc[min_idx, 'candle_gap_bottom']:
      df.loc[min_idx, 'candle_gap'] = df.loc[min_idx, 'candle_gap_color'] * 2

    # invalidate all gaps if there are too many gaps in the data
    up_gap_idxs = df.query('candle_gap == 2').index.tolist()
    down_gap_idxs = df.query('candle_gap == -2').index.tolist()
    if len(up_gap_idxs) > 10:
      up_gap_idxs = []
    if len(down_gap_idxs) > 10:
      down_gap_idxs = []

    # plot valid gaps
    gap_idxs = up_gap_idxs + down_gap_idxs
    for idx in gap_idxs:

      # gap start
      start = idx
      top_value = df.loc[start, 'candle_gap_top']
      bottom_value = df.loc[start, 'candle_gap_bottom']
      gap_color = 'green' if df.loc[start, 'candle_gap'] > 0 else 'red' # 'lightyellow' if df.loc[start, 'candle_gap'] > 0 else 'grey' # 
      gap_hatch = '||||' # '////' if df.loc[start, 'candle_gap'] > 0 else '\\\\\\\\' # 'xxxx'# 
      gap_hatch_color = 'black' # 'darkgreen' if df.loc[start, 'candle_gap'] > 0 else 'darkred' 
      
      # gap end
      end = None
      tmp_data = df[start:]
      for i, r in tmp_data.iterrows(): 
        if (r['candle_gap_top'] != top_value) or (r['candle_gap_bottom'] != bottom_value):  
          break      
        end = i

      # shift gap-start 1 day earlier
      pre_i = idxs.index(start)-1
      pre_start = idxs[pre_i] if pre_i > 0 else start
      tmp_data = df[start:end]
      ax.fill_between(df[pre_start:end].index, top_value, bottom_value, hatch=gap_hatch, facecolor=gap_color, interpolate=True, alpha=0.3, edgecolor=gap_hatch_color, linewidth=0.1, zorder=default_zorders['gap']) #,  

    # # gap support & resistant
    # ax.scatter(support_idx, df.loc[support_idx, 'Low'] * 0.98, marker='^', color='black', edgecolor='black', zorder=21)
    # ax.scatter(resistant_idx, df.loc[resistant_idx, 'High'] * 1.02, marker='v', color='black', edgecolor='black', zorder=21)

  # annotate close price, support/resistant(if exists)
  if 'support_resistant' in add_on:

    # annotate close price
    y_close = None
    y_text_close = None
    
    y_close_padding = padding*5
    y_close = df.loc[max_idx, 'Close'].round(2)
    y_text_close = y_close
    plt.annotate(f'{y_close}', xy=(max_x, y_text_close), xytext=(max_x, y_text_close), fontsize=13, xycoords='data', textcoords='data', color='black', va='center',  ha='left', bbox=dict(boxstyle="round", alpha=0))

    y_resistant = None
    y_text_resistant = None
    y_support = None
    y_text_support = None

    # annotate resistant
    if df.loc[max_idx, 'resistanter'] > '':
      resistant_score = abs(df.loc[max_idx, 'resistant_score'])
      y_resistant = df.loc[max_idx, 'resistant'].round(2)
      y_text_resistant = y_resistant

      diff = y_text_resistant - y_text_close
      if diff < y_close_padding:
        y_text_resistant = y_text_close + y_close_padding
      plt.annotate(f'{y_resistant}[{resistant_score}]', xy=(max_x, y_text_resistant), xytext=(max_x, y_text_resistant), fontsize=13, xycoords='data', textcoords='data', color='black', va='bottom',  ha='left', bbox=dict(boxstyle="round", facecolor='red', alpha=0.1*resistant_score))
    
    # annotate support 
    if df.loc[max_idx, 'supporter'] > '':
      support_score = abs(df.loc[max_idx, 'support_score'])
      y_support = df.loc[max_idx, 'support'].round(2)
      y_text_support = y_support
      
      diff = y_text_close - y_text_support
      if diff < y_close_padding:
        y_text_support = y_text_close - y_close_padding
      plt.annotate(f'{y_support}[{support_score}]', xy=(max_x, y_text_support), xytext=(max_x, y_text_support), fontsize=13, xycoords='data', textcoords='data', color='black', va='top',  ha='left', bbox=dict(boxstyle="round", facecolor='green', alpha=0.1*support_score))

  # annotate candle patterns
  if 'pattern' in add_on:
    
    # plot flat-top/bottom
    len_unit = datetime.timedelta(days=1)
    rect_high = padding*1.5
    for t in ['u', 'd']:
      t_idx = df.query(f'平头_trend == "{t}"').index
      t_color = 'green' if t == 'u' else 'red'
      for i in t_idx:
        x = idxs.index(i)
        x = x - 1 if x > 1 else x
        x = idxs[x]
        rect_len = (i - x) 
        x = x - (len_unit * 0.5)
        rect_len = rect_len + len_unit
        y = df.loc[i, 'Low'] - 2*padding if t == 'u' else df.loc[i, 'High'] + 0.5*padding
        flat = Rectangle((x, y), rect_len, rect_high, facecolor='yellow', edgecolor=t_color, linestyle='-', linewidth=1, fill=True, alpha=0.8, zorder=default_zorders['candle_pattern'])
        ax.add_patch(flat)
        
    # settings for annotate candle patterns
    pattern_info = {
      # '窗口_day': {1: '窗口', -1: '窗口'},
      # '反弹_day': {1: '反弹', -1: '回落'},
      # '突破_day': {1: '突破', -1: '跌落'},
      
      # '十字星_trend': {'u': '高浪线', 'd': '十字星'},
      '腰带_trend': {'u': '腰带', 'd': '腰带'},
      '锤子_trend': {'u': '锤子', 'd': '吊颈'},
      '流星_trend': {'u': '倒锤', 'd': '流星'},

      '穿刺_trend': {'u': '穿刺', 'd': '乌云'},
      # '平头_trend': {'u': '平底', 'd': '平顶'},
      '吞噬_trend': {'u': '吞噬', 'd': '吞噬'},
      '包孕_trend': {'u': '包孕', 'd': '包孕'},

      '启明黄昏_trend': {'u': '启明星', 'd': '黄昏星'},
      # 'linear_bounce_trend': {'u': '反弹', 'd': '回落'},
      # 'linear_break_trend': {'u': '突破', 'd': '跌落'}
    }
    settings = {
      'normal': {'fontsize':12, 'fontcolor':'black', 'va':'center', 'ha':'center', 'up':'green', 'down':'red', 'alpha': 0.15, 'arrowstyle': '-'},
      'emphasis': {'fontsize':12, 'fontcolor':'black', 'va':'center', 'ha':'center', 'up':'yellow', 'down':'purple', 'alpha': 0.15, 'arrowstyle': '-'},
    }

    # plot other patterns
    up_pattern_annotations = {}
    down_pattern_annotations = {}
    for p in pattern_info.keys():
      
      style = 'normal' if p not in ['窗口_trend', '突破_trend'] else 'emphasis' # , '反弹_trend'

      if p in df.columns:

        tmp_up_idx = df.query(f'{p} == "u"').index
        tmp_down_idx = df.query(f'{p} == "d"').index

        # positive patterns
        tmp_up_info = pattern_info[p]['u']
        if len(tmp_up_info) > 0: # and len(tmp_up_idx) < 10
          for i in tmp_up_idx:
            k = util.time_2_string(i.date())
            if k not in up_pattern_annotations: 
              up_pattern_annotations[k] = {'x': k, 'y': df.loc[i, 'Low'] - padding, 'text': tmp_up_info, 'style': style}
            else:
              up_pattern_annotations[k]['text'] = up_pattern_annotations[k]['text']  + f'/{tmp_up_info}'
              if up_pattern_annotations[k]['style'] == 'normal':
                up_pattern_annotations[k]['style'] = style 

        # negative patterns
        tmp_down_info = pattern_info[p]['d']
        if len(tmp_down_info) > 0: # and len(tmp_down_idx) < 10
          for i in tmp_down_idx:
            k = util.time_2_string(i.date())
            if k not in down_pattern_annotations:
              down_pattern_annotations[k] = {'x': k, 'y': df.loc[i, 'High'] + padding, 'text': tmp_down_info, 'style': style}
            else:
              down_pattern_annotations[k]['text'] = down_pattern_annotations[k]['text']  + f'/{tmp_down_info}'
              if down_pattern_annotations[k]['style'] == 'normal':
                down_pattern_annotations[k]['style'] = style 

    # candle pattern annotation
    annotations = {'up': up_pattern_annotations, 'down': down_pattern_annotations}
    y_text_padding = {0 : padding*0, 1: padding*5}
    for a in annotations.keys():
      
      # sort patterns by date
      tmp_a = annotations[a]
      tmp_annotation = {}
      sorted_keys = sorted(tmp_a.keys())
      for sk in sorted_keys:
        tmp_annotation[sk] = tmp_a[sk]

      # annotate patterns
      counter = 0
      for k in tmp_annotation.keys():

        x = tmp_annotation[k]['x']
        y = tmp_annotation[k]['y']
        text = tmp_annotation[k]['text']
        style = settings[tmp_annotation[k]['style']]
        if a == 'up':
          y_text = df.Low.min() - y_text_padding[counter % 2]
        else:
          y_text = df.High.max() + y_text_padding[counter % 2]
          
        plt.annotate(f'{text}', xy=(x, y), xytext=(x,y_text), fontsize=style['fontsize'], rotation=0, color=style['fontcolor'], va=style['va'],  ha=style['ha'], xycoords='data', textcoords='data', arrowprops=dict(arrowstyle=style['arrowstyle'], alpha=0.5, color='black'), bbox=dict(boxstyle="round", facecolor=style[a], edgecolor='none', alpha=style['alpha']))
        counter += 1

  # transform date to numbers, plot candlesticks
  # df.reset_index(inplace=True)
  # df[date_col] = df[date_col].apply(mdates.date2num)
  # plot_data = df[[date_col, open, high, low, close]]
  # ls, rs = candlestick_ohlc(ax=ax, quotes=plot_data.values, width=width, colorup=color['color_up'], colordown=color['color_down'], alpha=color['alpha'])
  
  # set offset, bar_width according to data interval
  if interval == 'day':
    OFFSET = datetime.timedelta(days=0.5)
    entity_width = datetime.timedelta(days=1)
  elif interval == 'week':
    OFFSET = datetime.timedelta(days=3.5)
    entity_width = datetime.timedelta(days=7)
  elif interval == 'month':
    OFFSET = datetime.timedelta(days=15)
    entity_width = datetime.timedelta(days=30)
  elif interval == 'year':
    OFFSET = datetime.timedelta(days=182.5)
    entity_width = datetime.timedelta(days=365)
  else:
    pass

  # set colors
  alpha = color['alpha'] 
  shadow_color = color['shadow_color']
  entity_edge_color = (0,0,0,0.1)
  ax.fill_between(df.index, df.loc[min_idx, 'High'], df.loc[min_idx, 'Low'], facecolor=None, interpolate=True, alpha=0, linewidth=1, zorder=default_zorders['candle_pattern'])

  # plot each candlestick
  for idx, row in df.iterrows():
    
    # set entity_color
    if row[close] >= row[open]:
      entity_color = color['color_up']
      lower = row[open]
      height = row[close] - row[open]
    else:
      entity_color = color['color_down']
      lower = row[close]
      height = row[open] - row[close]
    
    # set shadow_color
    if shadow_color is not None:
      line_color = shadow_color
    else:
      line_color = entity_color
    
    # plot shadow
    vline = Line2D(xdata=(idx, idx), ydata=(row[low], row[high]), color=line_color, linewidth=1, antialiased=True, zorder=default_zorders['candle_shadow'])
    
    # plot entity
    x = idx - OFFSET
    rect = Rectangle(xy=(x, lower), width=entity_width, height=height, facecolor=entity_color, linewidth=1, edgecolor=entity_edge_color, alpha=alpha, zorder=default_zorders['candle_entity'])

    # add shadow and entity to plot
    ax.add_line(vline)
    ax.add_patch(rect)
    
  ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
  ax.yaxis.set_ticks_position(default_plot_args['yaxis_position'])

  # return ax
  if use_ax is not None:
    return ax

# plot ichimoku chart
def plot_main_indicators(df, start=None, end=None, date_col='Date', add_on=['split', 'gap', 'support_resistant', 'pattern'], target_indicator = ['price', 'ichimoku', 'kama', 'candlestick', 'bb', 'psar', 'renko', 'linear'], interval='day', use_ax=None, title=None, candlestick_color=default_candlestick_color, ohlcv_col=default_ohlcv_col, plot_args=default_plot_args):
  """
  Plot ichimoku chart

  :param df: dataframe with ichimoku indicator columns
  :param start: start row to plot
  :param end: end row to plot
  :param date_col: column name of Date
  :param add_on: additional parts on candlestick
  :param target_indicator: indicators need to be ploted on the chart
  :param interval: interval of the sec_data, which dicides the width of candlestick
  :param use_ax: the already-created ax to draw on
  :param title: plot title
  :param ohlcv_col: columns names of Open/High/Low/Close/Volume
  :param candlestick_color: up/down color of candlestick
  :param plot_args: other plot arguments
  :returns: ichimoku plot
  :raises: none
  """
  # copy dataframe within a specific period
  ohlc_df = df[start:end].copy()
  max_idx = df.index.max()
  
  # add extention data
  extended = 3
  ext_columns = ['tankan', 'kijun', 'kama_fast', 'kama_slow']
  current_idx = max_idx
  next_idx = None
  period = 3
  if interval == "day":
    
    pred = add_ma_linear_features(df, period=period, target_col=ext_columns)

    for i in range(extended):
      next_idx = current_idx + datetime.timedelta(days = 1)

      for ec in ext_columns:
        slope = pred[ec][0]
        intercept = pred[ec][1]
        df.loc[next_idx, ec] = (period + i + 1) * ( slope) + intercept   
      current_idx = next_idx
  else:
    extended = None

  # create figure
  ax = use_ax
  if ax is None:
    fig = mpf.figure(figsize=plot_args['figsize'])
    ax = fig.add_subplot(1,1,1, style='yahoo')

  # as we usually ploting data within a year, therefore log_y is not necessary
  # ax.set_yscale("log")

  # plot close price
  if 'price' in target_indicator:
    alpha = 0.2
    ax.plot(df.index, df[default_ohlcv_col['close']], label='close', color='black', linestyle='--', alpha=alpha, zorder=default_zorders['price'])
  
  # plot renko bricks
  if 'renko' in target_indicator:
    ax = plot_renko(df, use_ax=ax, plot_args=default_plot_args, plot_in_date=True, close_alpha=0)
  
  # plot senkou lines, clouds, tankan and kijun
  if 'ichimoku' in target_indicator:
    alpha = 0.8
    ax.plot(df.index, df.tankan, label='tankan', color='green', linestyle='-', alpha=alpha, zorder=default_zorders['ichimoku']) # magenta
    ax.plot(df.index, df.kijun, label='kijun', color='red', linestyle='-', alpha=alpha, zorder=default_zorders['ichimoku']) # blue
    alpha = 0.25
    ax.fill_between(df.index, df.tankan, df.kijun, where=df.tankan > df.kijun, facecolor='green', interpolate=True, alpha=alpha, zorder=default_zorders['ichimoku'])
    ax.fill_between(df.index, df.tankan, df.kijun, where=df.tankan <= df.kijun, facecolor='red', interpolate=True, alpha=alpha, zorder=default_zorders['ichimoku'])
  
  # plot kama_fast/slow lines 
  if 'kama' in target_indicator:
    alpha = 0.8
    ax.plot(df.index, df.kama_fast, label='kama_fast', color='magenta', linestyle='-', alpha=alpha, zorder=default_zorders['kama']) # magenta
    ax.plot(df.index, df.kama_slow, label='kama_slow', color='blue', linestyle='-', alpha=alpha, zorder=default_zorders['kama'])

    # alpha = 0.1
    # ax.fill_between(df.index, df.kama_fast, df.kama_slow, where=df.kama_fast > df.kama_slow, facecolor='green', interpolate=True, alpha=alpha, zorder=-1)
    # ax.fill_between(df.index, df.kama_fast, df.kama_slow, where=df.kama_fast <= df.kama_slow, facecolor='red', interpolate=True, alpha=alpha, zorder=-1)
  
  # plot bollinger bands
  if 'bb' in target_indicator:
    alpha = 0.2
    alpha_fill = 0.02
    ax.plot(df.index, df.bb_high_band, label='bb_high_band', color='black', linestyle='-', alpha=alpha, zorder=default_zorders['default'])
    ax.plot(df.index, df.bb_low_band, label='bb_low_band', color='black', linestyle='-', alpha=alpha, zorder=default_zorders['default'])
    ax.plot(df.index, df.mavg, label='mavg', color='black', linestyle=':', alpha=alpha*3, zorder=default_zorders['default'])
    ax.fill_between(df.index, df.mavg, df.bb_high_band, facecolor='green', interpolate=True, alpha=alpha_fill, zorder=default_zorders['default'])
    ax.fill_between(df.index, df.mavg, df.bb_low_band, facecolor='red', interpolate=True, alpha=alpha_fill, zorder=default_zorders['default'])
  
  # plot average true range
  if 'atr' in target_indicator:
    alpha = 0.6
    ax.plot(df.index, df.atr, label='atr', color='green', alpha=alpha, zorder=default_zorders['default'])
    # ax.plot(df.index, df.bb_low_band, label='bb_low_band', color='red', alpha=alpha)
    # ax.plot(df.index, df.mavg, label='mavg', color='grey', alpha=alpha)
    # ax.fill_between(df.index, df.mavg, df.bb_high_band, facecolor='green', interpolate=True, alpha=0.1)
    # ax.fill_between(df.index, df.mavg, df.bb_low_band, facecolor='red', interpolate=True, alpha=0.2)
  
  # plot psar dots
  if 'psar' in target_indicator:
    alpha = 0.6
    s = 10
    ax.scatter(df.index, df.psar_up, label='psar', color='green', alpha=alpha, s=s, marker='o', zorder=default_zorders['default'])
    ax.scatter(df.index, df.psar_down, label='psar', color='red', alpha=alpha, s=s, marker='o', zorder=default_zorders['default'])
  
  # plot high/low trend
  if 'linear' in target_indicator:
    colors = {'u': 'green', 'd': 'red', 'n': 'orange', '': 'grey'}
    # hatches = {'u': '++', 'd': '--', 'n': '..', '': ''}
    # plot aroon_up/aroon_down lines 
    line_alpha = 0.5
    linear_direction = df.loc[max_idx, 'linear_direction']
    linear_color = colors[linear_direction]
    ax.plot(df.index, df.linear_fit_high, label='linear_fit_high', color=linear_color, linestyle='-.', alpha=line_alpha, zorder=default_zorders['default'])
    ax.plot(df.index, df.linear_fit_low, label='linear_fit_low', color=linear_color, linestyle='-.', alpha=line_alpha, zorder=default_zorders['default'])

    # fill between linear_fit_high and linear_fit_low
    fill_alpha = 0.25
    linear_range = df.linear_direction != ''
    linear_hatch = '--' # hatches[linear_direction]
    ax.fill_between(df.index, df.linear_fit_high, df.linear_fit_low, where=linear_range, facecolor='white', edgecolor=linear_color, hatch=linear_hatch, interpolate=True, alpha=fill_alpha, zorder=default_zorders['default'])    
  
  # plot candlestick
  if 'candlestick' in target_indicator:
    ax = plot_candlestick(df=ohlc_df, start=start, end=end, date_col=date_col, add_on=add_on, ohlcv_col=ohlcv_col, color=candlestick_color, use_ax=ax, plot_args=plot_args, interval=interval)
  
  # plot mask for extended
  if extended is not None:
    extended_data = df[ext_columns].tail(extended).copy()
    ax.plot(extended_data, linestyle=':', color='white', zorder=default_zorders['extended'])
  
  # title and legend
  ax.legend(bbox_to_anchor=plot_args['bbox_to_anchor'], loc=plot_args['loc'], ncol=plot_args['ncol'], borderaxespad=plot_args['borderaxespad']) 
  ax.set_title(title, rotation=plot_args['title_rotation'], x=plot_args['title_x'], y=plot_args['title_y'])
  ax.grid(True, axis='x', linestyle=':', linewidth=0.5)
  ax.yaxis.set_ticks_position(default_plot_args['yaxis_position'])
  
  # return ax
  if use_ax is not None:
    return ax

# plot aroon chart
def plot_aroon(df, start=None, end=None, use_ax=None, title=None, plot_args=default_plot_args):
  """
  Plot aroon chart

  :param df: dataframe with ichimoku indicator columns
  :param start: start row to plot
  :param end: end row to plot
  :param date_col: column name of Date
  :param ohlcv_col: columns names of Open/High/Low/Close/Volume
  :param use_ax: the already-created ax to draw on
  :param title: plot title
  :param plot_args: other plot arguments
  :returns: ichimoku plot
  :raises: none
  """
  # copy dataframe within a specific period
  df = df[start:end].copy()

  # create figure
  ax = use_ax
  if ax is None:
    fig = mpf.figure(figsize=plot_args['figsize'])
    ax = fig.add_subplot(1,1,1, style='yahoo')

  # plot aroon_up/aroon_down lines 
  ax.plot(df.index, df.aroon_up, label='aroon_up', color='green', marker='.', alpha=0.2)
  ax.plot(df.index, df.aroon_down, label='aroon_down', color='red', marker='.', alpha=0.2)

  # fill between aroon_up/aroon_down
  ax.fill_between(df.index, df.aroon_up, df.aroon_down, where=df.aroon_up > df.aroon_down, facecolor='green', interpolate=True, alpha=0.2)
  ax.fill_between(df.index, df.aroon_up, df.aroon_down, where=df.aroon_up <= df.aroon_down, facecolor='red', interpolate=True, alpha=0.2)

  # # plot waving areas
  # wave_idx = (df.aroon_gap_change==0)&(df.aroon_up_change==df.aroon_down_change)#&(df.aroon_up<96)&(df.aroon_down<96)
  # for i in range(len(wave_idx)):
  #   try:
  #     if wave_idx[i]:
  #         wave_idx[i-1] = True
  #   except Exception as e:
  #     print(e)
  # ax.fill_between(df.index, df.aroon_up, df.aroon_down, facecolor='grey', where=wave_idx, interpolate=False, alpha=0.3)

  # title and legend
  ax.legend(bbox_to_anchor=plot_args['bbox_to_anchor'], loc=plot_args['loc'], ncol=plot_args['ncol'], borderaxespad=plot_args['borderaxespad']) 
  ax.set_title(title, rotation=plot_args['title_rotation'], x=plot_args['title_x'], y=plot_args['title_y'])
  ax.grid(True, axis='both', linestyle='--', linewidth=0.5)

  # return ax
  if use_ax is not None:
    return ax

# plot renko chart
def plot_renko(df, start=None, end=None, use_ax=None, title=None, plot_in_date=True, close_alpha=0.5, save_path=None, save_image=False, show_image=False, plot_args=default_plot_args):
  
  # copy data frame
  df = df[start:end].copy()

  # create figure
  ax = use_ax
  if ax is None:
    fig = mpf.figure(figsize=plot_args['figsize'])
    ax = fig.add_subplot(1,1,1, style='yahoo')
    
  # plot close for displaying the figure
  ax.plot(df.Close, alpha=close_alpha)

  # whether to plot in date axes
  min_idx = df.index.min()
  max_idx = df.index.max()
  if df.loc[min_idx, 'renko_real'] != 'green' or df.loc[min_idx, 'renko_real'] != 'red':
    df.loc[min_idx, 'renko_real'] = df.loc[min_idx, 'renko_color'] 
    df.loc[min_idx, 'renko_countdown_days'] = df.loc[min_idx, 'renko_countdown_days'] 
  
  if plot_in_date:
    df = df.query('renko_real == "green" or renko_real =="red"').copy()
  else:
    df = df.query('renko_real == "green" or renko_real =="red"').reset_index()
  
  # plot renko
  legends = {'green': 'u', 'red': 'd', np.nan:' '}
  for index, row in df.iterrows():
    hatch = '----' # '/////' if row['renko_color'] == 'green' else '\\\\\\\\\\'
    facecolor = 'white'
    edgecolor = 'black'
    renko = Rectangle((index, row['renko_o']), row['renko_countdown_days'], row['renko_brick_height'], facecolor=facecolor, edgecolor=edgecolor, hatch=hatch, linestyle='-', linewidth=0.1, fill=False, alpha=0.4, label=legends[row['renko_real']], zorder=default_zorders['renko']) #  edgecolor=row['renko_color'], linestyle='-', linewidth=5, 
    legends[row['renko_real']] = "_nolegend_"
    ax.add_patch(renko, )
  
  # modify axes   
  if not plot_in_date:
    ax.get_figure().canvas.draw()
    xlabels = [item.get_text() for item in ax.get_xticklabels()]
    for i in range(len(xlabels)):  
      try:
        idx = int(xlabels[i])
        if idx in df.index:
          xlabels[i] = f'{df.loc[idx, "Date"].date()}'
        else:
          xlabels[i] = f'{df.index.max().date()}'
          continue
      except Exception as e:
        continue
    ax.set_xticklabels(xlabels)
  
  # title and legend
  ax.legend(bbox_to_anchor=plot_args['bbox_to_anchor'], loc=plot_args['loc'], ncol=plot_args['ncol'], borderaxespad=plot_args['borderaxespad']) 
  ax.set_title(title, rotation=plot_args['title_rotation'], x=plot_args['title_x'], y=plot_args['title_y'])
  # ax.grid(True, axis='x', linestyle='--', linewidth=0.5)

  ax.yaxis.set_ticks_position(default_plot_args['yaxis_position'])
  
  # return ax
  if use_ax is not None:
    return ax
  else:
    # save image
    if save_image and (save_path is not None):
      plt.savefig(save_path + title + '.png')
      
    # show image
    if show_image:
      plt.show()

# plot rate and trigger_score/trend_score for each target list
def plot_summary(data, width=20, unit_size=0.3, wspace=0, hspace=0.4, plot_args=default_plot_args, config=None, save_path=None):
  """
  Plot rate and trigger_score/trend_score for each target list
  :param data: dict of dataframes including 'result'
  :param figsize:  figure size
  :param save_path:  path to save the figure
  :returns: none
  :raises: none
  """

  # get pools
  pools = list(data['result'].keys())
  n_row = len(pools)
  num_symbols = [len(data['result'][x]) for x in data['result'].keys()]

  # create axes for each indicator
  fig = plt.figure(figsize=(width, sum(num_symbols)*unit_size))  
  gs = gridspec.GridSpec(n_row, 2, height_ratios=num_symbols, width_ratios=[1,1])
  gs.update(wspace=wspace, hspace=hspace)
  axes = {}

  # plot rate and score
  for i in range(n_row):

    num_total = num_symbols[i]
    num_down = 0

    # get target data
    t = pools[i]
    tmp_data = data['result'][t][['symbol', 'rate', 'trigger_score', 'trend_score']].set_index('symbol')
    tmp_data['name'] = tmp_data.index.values

    # get data
    if 'a_company' in t:
      if config is not None:
        names = config['visualization']['plot_args']['sec_name']
        for idx, row in tmp_data.iterrows():
          tmp_name = names.get(idx)
          if tmp_name is not None:
            tmp_data.loc[idx, 'name'] = tmp_name
    tmp_data = tmp_data.set_index('name')
    tmp_data = tmp_data.sort_values('trigger_score', ascending=True)
    tmp_data['rate'] = tmp_data['rate'] * 100

    # get ax
    if i == 0:
      rate_ax = plt.subplot(gs[i*2], zorder=1) 
      score_ax = plt.subplot(gs[i*2+1], zorder=0)
      axes['rate'] = rate_ax
      axes['score'] = score_ax
    else:
      rate_ax = plt.subplot(gs[i*2], sharex=axes['rate'], zorder=1) 
      score_ax = plt.subplot(gs[i*2+1], sharex=axes['score'], zorder=0)
      
    # plot rate
    tmp_data['rate_color'] = 'green'
    down_idx = tmp_data.query('rate <= 0').index    
    tmp_data.loc[down_idx, 'rate_color'] = 'red'
    num_down = len(down_idx)
    title_color = 'green' if num_total/2 > num_down else 'red'  
    rate_ax.barh(tmp_data.index, tmp_data['rate'], color=tmp_data['rate_color'], label='rate', alpha=0.5) #, edgecolor='k'
    rate_ax.set_title(f'{t.replace("_day", "")} Rate ({num_total-num_down}/{num_total})', fontsize=25, bbox=dict(boxstyle="round", fc=title_color, ec="1.0", alpha=0.1))
    rate_ax.grid(True, axis='x', linestyle='--', linewidth=0.5, alpha=0.3)
    rate_ax.grid(True, axis='y', linestyle='-', linewidth=0.5, alpha=1)
    rate_ax.yaxis.set_ticks_position("left")
    # rate_ax.spines['right'].set_alpha(0)
    # plt.setp(rate_ax.get_yticklabels(), visible=False)

    # plot trigger score
    score_ax.barh(tmp_data.index, tmp_data.trigger_score, color='yellow', label='trigger_score', alpha=0.5, edgecolor='k')
    tmp_data['score_bottom'] = tmp_data['trigger_score']
    for index, row in tmp_data.iterrows():
      if (row['trigger_score'] > 0 and row['trend_score'] > 0) or (row['trigger_score'] < 0 and row['trend_score'] < 0):
        continue
      else:
        tmp_data.loc[index, 'score_bottom'] = 0

    # plot score
    tmp_data['score_color'] = 'green'
    down_idx = tmp_data.query('trend_score <= 0').index    
    tmp_data.loc[down_idx, 'score_color'] = 'red'
    score_ax.barh(tmp_data.index, tmp_data['trend_score'], color=tmp_data['score_color'], left=tmp_data['score_bottom'],label='trend_score', alpha=0.5) #, edgecolor='k'  
    score_ax.set_title(f'{t.replace("_day", "")} Trend Score', fontsize=25, bbox=dict(boxstyle="round", fc=title_color, ec="1.0", alpha=0.1))
    score_ax.legend(bbox_to_anchor=plot_args['bbox_to_anchor'], loc=plot_args['loc'], ncol=plot_args['ncol'], borderaxespad=plot_args['borderaxespad']) 
    score_ax.grid(True, axis='x', linestyle='--', linewidth=0.5, alpha=0.3)
    score_ax.grid(True, axis='y', linestyle='-', linewidth=0.5, alpha=1)
    score_ax.spines['left'].set_alpha(0)
    plt.setp(score_ax.get_yticklabels(), visible=False)
    # score_ax.yaxis.set_ticks_position("right")

  # save image
  if save_path is not None:
    plt.savefig(save_path, bbox_inches = 'tight')

  return score_ax

# plot general ta indicators
def plot_indicator(df, target_col, start=None, end=None, signal_x='signal', signal_y='Close', benchmark=None, boundary=None, color_mode=None, use_ax=None, title=None, plot_price_in_twin_ax=False, trend_val=default_trend_val, signal_val=default_signal_val, plot_args=default_plot_args):
  """
  Plot indicators around a benchmark

  :param df: dataframe which contains target columns
  :param target_col: columnname of the target indicator
  :param start: start date of the data
  :param end: end of the data
  :param signal_x: columnname of the signal x values (default 'signal')
  :param signal_y: columnname of the signal y values (default 'Close')
  :param benchmark: benchmark, a fixed value
  :param boundary: upper/lower boundaries, a list of fixed values
  :param color_mode: which color mode to use: benckmark/up_down
  :param use_ax: the already-created ax to draw on
  :param title: title of the plot
  :param plot_price_in_twin_ax: whether plot price and signal in a same ax or in a twin ax
  :param trend_val: value of different kind of trends (e.g. 'u'/'d'/'n')
  :param signal_val: values of different kind of signals
  :param plot_args: other plot arguments
  :returns: figure with indicators and close price plotted
  :raises: none
  """
  # select data
  df = df[start:end].copy() 
  
  # create figure
  ax = use_ax
  if ax is None:
    fig = mpf.figure(figsize=plot_args['figsize'])
    ax = fig.add_subplot(1,1,1, style='yahoo')

  # plot benchmark
  if benchmark is not None:
    df['benchmark'] = benchmark
    ax.plot(df.index, df['benchmark'], color='black', linestyle='-', label='%s'%benchmark, alpha=0.3)

  # plot boundary
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
  # for col in target_col:
  #   ax.plot(df.index, df[col], label=col, alpha=0.5)

  # plot color bars if there is only one indicator to plot
  if len(target_col) == 1:
    tar = target_col[0]

    # plot in up_down mode
    if color_mode == 'up_down':  
      df['color'] = 'red'
      previous_target_col = 'previous_' + tar
      df[previous_target_col] = df[tar].shift(1)
      df.loc[df[tar] > df[previous_target_col], 'color'] = 'green'
      df.loc[df[tar] == df[previous_target_col], 'color'] = 'orange'

      target_max = df[target_col].values.max()
      target_min = df[target_col].values.min()

      df.loc[df[tar] >= target_max, 'color'] = 'green'
      df.loc[df[tar] <= target_min, 'color'] = 'red'

    # plot in benchmark mode
    elif color_mode == 'benchmark' and benchmark is not None:
      df['color'] = 'red'
      df.loc[df[tar] > benchmark, 'color'] = 'green'

    # plot indicator
    if 'color' in df.columns:
      ax.bar(df.index, height=df[tar], color=df.color, alpha=0.3)

  # plot close price
  if signal_y in df.columns:
    if plot_price_in_twin_ax:
      ax2=ax.twinx()
      plot_signal(df, signal_x=signal_x, signal_y=signal_y, trend_val=trend_val, signal_val=signal_val, use_ax=ax2)
      ax2.legend(loc='lower left')
    else:
      plot_signal(df, signal_x=signal_x, signal_y=signal_y, trend_val=trend_val, signal_val=signal_val, use_ax=ax)

  # plot title and legend
  ax.legend(bbox_to_anchor=plot_args['bbox_to_anchor'], loc=plot_args['loc'], ncol=plot_args['ncol'], borderaxespad=plot_args['borderaxespad']) 
  ax.set_title(title, rotation=plot_args['title_rotation'], x=plot_args['title_x'], y=plot_args['title_y'])

  ax.yaxis.set_ticks_position(default_plot_args['yaxis_position'])

  # return ax
  if use_ax is not None:
    return ax

# plot multiple indicators on a same chart
def plot_multiple_indicators(df, args={}, start=None, end=None, interval='day', save_path=None, save_image=False, show_image=False, title=None, width=35, unit_size=3, wspace=0, hspace=0.015, subplot_args=default_plot_args):
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
  :param subplot_args: plot args for subplots
  :returns: plot
  :raises: none
  """
  
  # select plot data
  plot_data = df[start:end].copy()

  interval_factor = {'day': 1, 'week': 7, 'month': 30}
  start = util.time_2_string(plot_data.index.min())
  end = util.time_2_string(plot_data.index.max())
  width = util.num_days_between(start, end) / interval_factor[interval] * 0.125

  # get indicator names and plot ratio
  plot_ratio = args.get('plot_ratio')
  if plot_ratio is None :
    print('No indicator to plot')
    return None
  indicators = list(plot_ratio.keys())
  ratios = list(plot_ratio.values())
  num_indicators = len(indicators)
  
  # create axes for each indicator
  fig = plt.figure(figsize=(width, num_indicators*unit_size))  
  gs = gridspec.GridSpec(num_indicators, 1, height_ratios=ratios)
  gs.update(wspace=wspace, hspace=hspace)
  axes = {}
  for i in range(num_indicators):
    tmp_indicator = indicators[i]
    tmp_args = args.get(tmp_indicator)
    
    # put the main_indicators at the bottom, share_x
    if i == 0:
      axes[tmp_indicator] = plt.subplot(gs[i]) 
    else:
      axes[tmp_indicator] = plt.subplot(gs[i], sharex=axes[indicators[0]])
      
    # shows the x_ticklabels on the top at the first ax
    if i != 0: #i%2 == 0: # 
      axes[tmp_indicator].xaxis.set_ticks_position("none")
      plt.setp(axes[tmp_indicator].get_xticklabels(), visible=False)
      axes[tmp_indicator].patch.set_alpha(0.5)
    else:
      axes[tmp_indicator].xaxis.set_ticks_position("top")
      axes[tmp_indicator].patch.set_alpha(0.5)

    # set border color
    spine_alpha = 0.3
    for position in ['top', 'bottom', 'left', 'right']:
      if (i in [1, 2, 3] and position in ['top']) or (i in [0] and position in ['bottom']):
        axes[tmp_indicator].spines[position].set_alpha(0)
      else:
        axes[tmp_indicator].spines[position].set_alpha(spine_alpha)

    # get extra arguments
    target_col = tmp_args.get('target_col')
    signal_y = tmp_args.get('signal_y')
    signal_x = tmp_args.get('signal_x')
    trend_val = tmp_args.get('trend_val')
    signal_val = tmp_args.get('signal_val')
    benchmark = tmp_args.get('benchmark')
    boundary = tmp_args.get('boundary')
    color_mode = tmp_args.get('color_mode')
    plot_price_in_twin_ax = tmp_args.get('plot_price_in_twin_ax')
    trend_val = trend_val if trend_val is not None else default_trend_val
    signal_val = signal_val if signal_val is not None else default_signal_val
    plot_price_in_twin_ax = plot_price_in_twin_ax if plot_price_in_twin_ax is not None else False

    # plot ichimoku with candlesticks
    if tmp_indicator == 'main_indicators':
      # get candlestick width and color
      candlestick_color = tmp_args.get('candlestick_color') if tmp_args.get('candlestick_color') is not None else default_candlestick_color
      width = tmp_args.get('candlestick_width') if tmp_args.get('candlestick_width') is not None else 1
      target_indicator = tmp_args.get('target_indicator') if tmp_args.get('target_indicator') is not None else ['price']

      plot_main_indicators(
        df=plot_data, target_indicator=target_indicator, interval=interval, candlestick_color=candlestick_color,
        use_ax=axes[tmp_indicator], title=tmp_indicator, plot_args=subplot_args)

    # plot aroon
    elif tmp_indicator == 'aroon':
      plot_aroon(df=plot_data, use_ax=axes[tmp_indicator], title=tmp_indicator, plot_args=subplot_args)

    # plot adx
    elif tmp_indicator == 'adx':
      plot_adx(df=plot_data, use_ax=axes[tmp_indicator], title=tmp_indicator, plot_args=subplot_args)

    # plot volume  
    elif tmp_indicator == 'volume':
      
      alpha = tmp_args.get('alpha') if tmp_args.get('alpha') is not None else 1
      
      # set bar_width according to data interval
      bar_width = 0.8
      if interval == 'day':
        bar_width = datetime.timedelta(days=1)
      elif interval == 'week':
        bar_width = datetime.timedelta(days=7)
      elif interval == 'month':
        bar_width = datetime.timedelta(days=30)
      elif interval == 'year':
        bar_width = datetime.timedelta(days=365)
      else:
        pass

      plot_bar(df=plot_data, target_col=target_col, width=bar_width, alpha=alpha, color_mode=color_mode, benchmark=None, title=tmp_indicator, use_ax=axes[tmp_indicator], plot_args=default_plot_args)

    # plot renko
    elif tmp_indicator == 'renko':
      plot_in_date = tmp_args.get('plot_in_date') if tmp_args.get('plot_in_date') is not None else True
      plot_renko(plot_data, use_ax=axes[tmp_indicator], title=tmp_indicator, plot_args=default_plot_args, plot_in_date=plot_in_date)

    # plot ta signals or candle patterns
    elif tmp_indicator == 'signals' or tmp_indicator == 'candle':
      signals = tmp_args.get('signal_list')
      signal_bases = []
      signal_names = []
      if signals is not None:
        for i in range(len(signals)):
          signal_name = signals[i]
          signal_names.append(signal_name.split('_')[0])
          plot_data[f'signal_base_{signal_name}'] = i
          signal_bases.append(i)
          plot_signal(
            df=plot_data, signal_x=signal_name, signal_y=f'signal_base_{signal_name}', 
            title=tmp_indicator, use_ax=axes[tmp_indicator], trend_val=trend_val, signal_val=signal_val, plot_args=subplot_args)

      # legend and title
      plt.ylim(ymin=min(signal_bases)-1 , ymax=max(signal_bases)+1)
      plt.yticks(signal_bases, signal_names)
      axes[tmp_indicator].legend().set_visible(False)

    # plot trend idx
    elif tmp_indicator == 'trend_idx':
      plot_up_down(df=plot_data, col='trend_idx', use_ax=axes[tmp_indicator], title=tmp_indicator)
      
    # plot score and trigger score
    elif tmp_indicator == 'score':
      plot_score(df=plot_data, use_ax=axes[tmp_indicator], title=tmp_indicator, plot_args=subplot_args)

    # plot other indicators
    else:
      plot_indicator(
        df=plot_data, target_col=target_col, 
        signal_x=signal_x, signal_y=signal_y, signal_val=signal_val, 
        plot_price_in_twin_ax=plot_price_in_twin_ax, 
        benchmark=benchmark, boundary=boundary, color_mode=color_mode,
        title=tmp_indicator, use_ax=axes[tmp_indicator], plot_args=subplot_args)

  # adjust plot layout
  max_idx = df.index.max()
  up_down_symbol = {True: '↑', False: '↓'}

  close_rate = (df.loc[max_idx, "rate"]*100).round(2)
  title_color = 'green' if close_rate > 0 else 'red'
  title_symbol = up_down_symbol[close_rate > 0]
  plt.rcParams['font.sans-serif'] = ['SimHei'] 
  plt.rcParams['axes.unicode_minus'] = False

  # get name of the symbol, and linear/candle/adx descriptions
  new_title = args['sec_name'].get(title.split('(')[0]) 
  
  # score description
  score_desc = ''
  for term in ['', 'inday', 'short', 'middle', 'long']:
    score_col = f'{term}_trend_score' if term != '' else 'trend_score'
    socre_change_col = f'{score_col}_change'
    term_score = df.loc[max_idx, score_col]
    term_score_change = round(df.loc[max_idx, socre_change_col],2)
    term_symbol = up_down_symbol[df.loc[max_idx, socre_change_col] > 0]
    term_desc = f'{term_score}({term_score_change}{term_symbol})' if term == '' else f'{term_score}{term_symbol}'
  
    if term == '':
      score_desc += term_desc + ' = '
    elif term in ['inday', 'short', 'middle', 'long']:
      if term_score < 0:
        score_desc +=  ' ' + term_desc
      else:
        score_desc += ' + ' + term_desc
    else:
      print(f'unknown term {term}')

  inday_desc = f'[{df.loc[max_idx, "up_score_description"]} | {df.loc[max_idx, "down_score_description"]}]'
  inday_desc = inday_desc.replace(', ]', ']')#.replace('; ', '')
  
  # construct super title
  if new_title is None:
    new_title == ''
  super_title = f'{title}({new_title})  {close_rate}% {title_symbol}'
  super_title = f'{super_title}\n{score_desc}'
  super_title = f'{super_title}\n{inday_desc}'
  
  fig.suptitle(f'{super_title}', x=0.5, y=1.05, fontsize=22, bbox=dict(boxstyle="round", fc=title_color, ec="1.0", alpha=0.1), linespacing = 1.8)

  # save image
  if save_image and (save_path is not None):
    plt_save_name = save_path + title + '.png'
    plt.savefig(plt_save_name, bbox_inches = 'tight')

  # show image
  if show_image:
    plt.show()

  # close figures
  plt.cla()
  plt.clf()
  plt.close()

# calculate ta indicators, trend and derivatives for historical data
def plot_historical_evolution(df, symbol, interval, config, his_start_date=None, his_end_date=None, indicators=default_indicators, is_print=False, create_gif=False, plot_final=False, remove_origin=True, plot_save_path=None):
  """
  Calculate selected ta features for dataframe

  :param df: original dataframe with hlocv features
  :param symbol: symbol of the data
  :param interval: interval of the data
  :param his_start_date: start date
  :param his_end_date: end_date
  :param indicators: indicators to calculate
  :param is_print: whether to print current progress
  :param create_gif: whether to create gif from images
  :param plot_final: whether to combine all images to a final one
  :param plot_save_path: path to save plots
  :param remove_origin: whether to remove original images for each day
  :returns: dataframe with ta features, derivatives, signals
  :raises: None
  """
  # copy dataframe
  df = df.copy()

  df_max_idx = util.time_2_string(df.index.max())
  if df_max_idx < his_end_date:
    print(f'can only evolve to {df_max_idx}')
    his_end_date = df_max_idx
  
  if df is None or len(df) == 0:
    print(f'{symbol}: No data for calculation')
    return None   
  else:
    data_start_date = util.string_plus_day(string=his_start_date, diff_days=-config['calculation']['look_back_window'][interval])
    df = df[data_start_date:]
    plot_start_date = data_start_date

  if create_gif or plot_final:
    if plot_save_path is None:
      print('Please specify plot save path in parameters, create_gif disable for this time')
      create_gif = False
    else:
      config['visualization']['show_image'] = False
      config['visualization']['save_image'] = True
      images = []
  
  try:
    
    # preprocess sec_data
    phase = 'preprocess'
    df = preprocess(df=df, symbol=symbol)
    
    # calculate TA indicators
    phase = 'cal_ta_basic_features' 
    df = calculate_ta_basic(df=df, indicators=indicators)
    
    # calculate TA trend
    phase = 'cal_ta_static_features'
    df = calculate_ta_static(df=df, indicators=indicators)
    
    # calculate TA derivatives for historical data for period [his_start_date ~ his_end_date]
    phase = 'cal_ta_dynamic_features_and_signals'
    historical_ta_data = pd.DataFrame()
    ed = his_start_date

    current_max_idx = None
    while ed <= his_end_date:   

      # calculate sd = ed - interval, et max_idx in df[sd:ed]
      sd = util.string_plus_day(string=ed, diff_days=-config['visualization']['plot_window'][interval])
      tmp_max_idx = df[sd:ed].index.max()
      
      # decide whether to skip current loop
      skip = False
      if current_max_idx is not None and tmp_max_idx <= current_max_idx:
        skip = True

      # update current_max_idx
      if (current_max_idx is None) or (tmp_max_idx > current_max_idx):
        current_max_idx = tmp_max_idx

      # calculation and visualization
      if skip:
        if is_print:
          print(f'{ed} - ({sd} ~ {util.time_2_string(tmp_max_idx)}) - skip')

      else:
        if is_print:
          print(f'{ed} - ({sd} ~ {util.time_2_string(tmp_max_idx)})')
        
        # calculate the dynamic part: linear features
        ta_data = calculate_ta_dynamic(df=df[sd:ed])
        ta_data = calculate_ta_signal(df=ta_data)
        historical_ta_data = pd.concat([historical_ta_data, ta_data.tail(1)])

        # create image for gif
        if create_gif:
          visualization(df=ta_data, start=plot_start_date, title=f'{symbol}({ed})', save_path=plot_save_path, visualization_args=config['visualization'])
          images.append(f'{plot_save_path}{symbol}({ed}).png')

      # update ed
      ed = util.string_plus_day(string=ed, diff_days=1)

    # append data
    historical_ta_data = ta_data.append(historical_ta_data)  
    df = util.remove_duplicated_index(df=historical_ta_data, keep='last')

    # create gif
    if create_gif:
      util.image_2_gif(image_list=images, save_name=f'{plot_save_path}{symbol}({his_start_date}-{his_end_date}).gif')

    # remove original images
    if remove_origin:
      for img in images:
        os.remove(img)

    # if plot final data
    if plot_final: 
      visualization(df=df, start=plot_start_date, title=f'{symbol}(final)', save_path=plot_save_path, visualization_args=config['visualization'])

  except Exception as e:
    print(symbol, phase, e)

  return df


