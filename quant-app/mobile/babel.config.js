module.exports = function (api) {
  api.cache(true);
  return {
    presets: ['babel-preset-expo'],
    plugins: [
      // expo-router requires reanimated's plugin to be listed last.
      'react-native-reanimated/plugin',
    ],
  };
};
