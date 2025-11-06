// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title FlashloanArbitrage
 * @notice Ultra-optimized MEV Bot Contract
 * @dev All interfaces included inline to avoid import errors
 */

// ============================================================================
// INTERFACES (Inline - No External Dependencies)
// ============================================================================

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

interface IUniswapV2Router {
    function swapExactTokensForTokens(
        uint amountIn,
        uint amountOutMin,
        address[] calldata path,
        address to,
        uint deadline
    ) external returns (uint[] memory amounts);
    
    function getAmountsOut(uint amountIn, address[] calldata path) 
        external view returns (uint[] memory amounts);
}

interface IUniswapV3Router {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }
    
    function exactInputSingle(ExactInputSingleParams calldata params) 
        external payable returns (uint256 amountOut);
}

interface IFlashLoanSimpleReceiver {
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external returns (bool);
}

interface IPoolAddressesProvider {
    function getPool() external view returns (address);
}

interface IPool {
    function flashLoanSimple(
        address receiverAddress,
        address asset,
        uint256 amount,
        bytes calldata params,
        uint16 referralCode
    ) external;
}

// ============================================================================
// SECURITY GUARDS
// ============================================================================

abstract contract ReentrancyGuard {
    uint256 private constant NOT_ENTERED = 1;
    uint256 private constant ENTERED = 2;
    uint256 private _status;

    constructor() {
        _status = NOT_ENTERED;
    }

    modifier nonReentrant() {
        require(_status != ENTERED, "ReentrancyGuard: reentrant call");
        _status = ENTERED;
        _;
        _status = NOT_ENTERED;
    }
}

abstract contract Ownable {
    address private _owner;
    address private _authorizedExecutor;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event ExecutorUpdated(address indexed executor);

    constructor() {
        _owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
    }

    modifier onlyOwner() {
        require(msg.sender == _owner, "Ownable: caller is not the owner");
        _;
    }

    modifier onlyAuthorizedExecutor() {
        require(msg.sender == _authorizedExecutor || msg.sender == _owner, "Not authorized");
        _;
    }

    function setExecutor(address executor) external onlyOwner {
        _authorizedExecutor = executor;
        emit ExecutorUpdated(executor);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Ownable: zero address");
        emit OwnershipTransferred(_owner, newOwner);
        _owner = newOwner;
    }

    function owner() public view returns (address) {
        return _owner;
    }
    
    function executor() public view returns (address) {
        return _authorizedExecutor;
    }
}

// ============================================================================
// MAIN CONTRACT
// ============================================================================

contract FlashloanArbitrage is ReentrancyGuard, Ownable, IFlashLoanSimpleReceiver {
    
    // Aave V3 Pool (Polygon Mainnet)
    address private constant AAVE_POOL = 0x794a61358D6845594F94dc1DB02A252b5b4814aD;
    
    // Flashloan premium (0.09% = 9 basis points)
    uint256 private constant FLASHLOAN_PREMIUM_BPS = 9;
    uint256 private constant PREMIUM_DENOMINATOR = 10000;
    
    // Price manipulation guard (max 5% impact)
    uint256 private constant MAX_PRICE_IMPACT = 500;
    uint256 private constant PRICE_IMPACT_DENOMINATOR = 10000;
    
    // Emergency pause
    bool public paused;
    
    // Events
    event ArbitrageExecuted(address indexed token, uint256 profit);
    event FlashloanExecuted(address indexed asset, uint256 amount, uint256 profit);
    event EmergencyPaused(address indexed by);
    event ProfitWithdrawn(address indexed to, address indexed token, uint256 amount);
    
    constructor() {
        paused = false;
    }
    
    // ========================================================================
    // MAIN FUNCTIONS
    // ========================================================================
    
    function executeFlashLoan(
        address asset,
        uint256 amount,
        bytes calldata params
    ) external onlyAuthorizedExecutor nonReentrant {
        require(!paused, "Contract paused");
        
        IPool(AAVE_POOL).flashLoanSimple(
            address(this),
            asset,
            amount,
            params,
            0
        );
    }
    
    function executeOperation(
        address asset,
        uint256 amount,
        uint256 premium,
        address initiator,
        bytes calldata params
    ) external override returns (bool) {
        require(msg.sender == AAVE_POOL, "Caller must be Aave Pool");
        require(initiator == address(this), "Initiator must be this contract");
        
        // Decode parameters
        (
            uint8 strategyType,
            address[] memory path,
            address[] memory routers,
            uint256[] memory amountsOutMin
        ) = abi.decode(params, (uint8, address[], address[], uint256[]));
        
        uint256 balanceBefore = IERC20(asset).balanceOf(address(this));
        
        // Execute strategy
        if (strategyType == 1) {
            _executeDirectArbitrage(asset, amount, path, routers, amountsOutMin);
        } else if (strategyType == 2) {
            _executeTriangularArbitrage(asset, amount, path, routers, amountsOutMin);
        }
        
        uint256 balanceAfter = IERC20(asset).balanceOf(address(this));
        uint256 totalDebt = amount + premium;
        
        require(balanceAfter >= totalDebt, "Insufficient funds to repay");
        
        // Approve and repay
        IERC20(asset).approve(AAVE_POOL, totalDebt);
        
        uint256 profit = balanceAfter - totalDebt;
        emit FlashloanExecuted(asset, amount, profit);
        
        return true;
    }
    
    // ========================================================================
    // INTERNAL STRATEGIES
    // ========================================================================
    
    function _executeDirectArbitrage(
        address asset,
        uint256 amount,
        address[] memory path,
        address[] memory routers,
        uint256[] memory amountsOutMin
    ) private {
        require(path.length >= 2, "Invalid path");
        require(routers.length == 2, "Need 2 routers");
        
        // Swap 1: Buy on DEX A
        IERC20(path[0]).approve(routers[0], amount);
        IUniswapV2Router(routers[0]).swapExactTokensForTokens(
            amount,
            amountsOutMin[0],
            path,
            address(this),
            block.timestamp + 300
        );
        
        // Swap 2: Sell on DEX B
        uint256 intermediateBalance = IERC20(path[path.length - 1]).balanceOf(address(this));
        
        address[] memory reversePath = new address[](path.length);
        for (uint i = 0; i < path.length; i++) {
            reversePath[i] = path[path.length - 1 - i];
        }
        
        IERC20(reversePath[0]).approve(routers[1], intermediateBalance);
        IUniswapV2Router(routers[1]).swapExactTokensForTokens(
            intermediateBalance,
            amountsOutMin[1],
            reversePath,
            address(this),
            block.timestamp + 300
        );
        
        emit ArbitrageExecuted(asset, IERC20(asset).balanceOf(address(this)));
    }
    
    function _executeTriangularArbitrage(
        address asset,
        uint256 amount,
        address[] memory path,
        address[] memory routers,
        uint256[] memory amountsOutMin
    ) private {
        require(path.length == 4, "Triangular requires 4 tokens");
        require(path[0] == path[3], "Must start and end with same token");
        
        uint256 currentAmount = amount;
        
        // Execute 3 swaps (A->B, B->C, C->A)
        for (uint i = 0; i < 3; i++) {
            address[] memory swapPath = new address[](2);
            swapPath[0] = path[i];
            swapPath[1] = path[i + 1];
            
            IERC20(swapPath[0]).approve(routers[i], currentAmount);
            
            uint[] memory amounts = IUniswapV2Router(routers[i]).swapExactTokensForTokens(
                currentAmount,
                amountsOutMin[i],
                swapPath,
                address(this),
                block.timestamp + 300
            );
            
            currentAmount = amounts[amounts.length - 1];
        }
        
        emit ArbitrageExecuted(asset, currentAmount);
    }
    
    // ========================================================================
    // ADMIN FUNCTIONS
    // ========================================================================
    
    function withdrawProfits(address token, address to) external onlyOwner nonReentrant {
        require(to != address(0), "Invalid recipient");
        
        uint256 balance = IERC20(token).balanceOf(address(this));
        require(balance > 0, "No profits");
        
        IERC20(token).transfer(to, balance);
        emit ProfitWithdrawn(to, token, balance);
    }
    
    function withdrawETH(address payable to) external onlyOwner {
        require(to != address(0), "Invalid recipient");
        uint256 balance = address(this).balance;
        require(balance > 0, "No ETH");
        
        (bool success, ) = to.call{value: balance}("");
        require(success, "Transfer failed");
    }
    
    function emergencyPause() external onlyOwner {
        paused = true;
        emit EmergencyPaused(msg.sender);
    }
    
    function unpause() external onlyOwner {
        paused = false;
    }
    
    receive() external payable {}
}