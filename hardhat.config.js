require("@nomiclabs/hardhat-waffle");
require("dotenv").config();

module.exports = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200000  // Extreme gas optimization
      },
      viaIR: true  // Enable Yul optimizer
    }
  },
  networks: {
    polygon: {
      url: process.env.ALCHEMY_RPC_URL || "",
      accounts: [process.env.ADMIN_PRIVATE_KEY],
      chainId: 137,
      gasPrice: 50000000000  // 50 gwei
    },
    mumbai: {
      url: process.env.TESTNET_RPC || "",
      accounts: [process.env.ADMIN_PRIVATE_KEY],
      chainId: 80001
    }
  },
  paths: {
    sources: "./contracts",
    tests: "./tests",
    cache: "./cache",
    artifacts: "./artifacts"
  }
};