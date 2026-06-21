"""
Direct PancakeSwap V2 executor — bypasses TWAK for on-chain swap execution.
Uses web3.py + BSC RPC. Mnemonic is read from macOS keychain at init and
held in memory only — never written to disk.
"""

import hashlib
import binascii
import json
import logging
import os
import subprocess
import time
from typing import Optional

import requests
from web3 import Web3
from eth_account import Account

log = logging.getLogger(__name__)

Account.enable_unaudited_hdwallet_features()

# ── BSC constants ──────────────────────────────────────────────────────────────
BSC_RPC       = "https://bsc-dataseed1.binance.org/"
BSC_RPC_ALT   = "https://bsc-dataseed2.binance.org/"
CHAIN_ID      = 56
PANCAKE_V2    = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
WBNB          = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
USDT_BSC      = "0x55d398326f99059fF775485246999027B3197955"

# ── Hardcoded BSC token addresses ─────────────────────────────────────────────
_TOKEN_MAP: dict[str, str] = {
    "USDT":  "0x55d398326f99059fF775485246999027B3197955",
    "USDC":  "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    "BNB":   "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "WBNB":  "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "ETH":   "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
    "BTCB":  "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",
    "CAKE":  "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
    "XVS":   "0xcF6BB5389c92Bdda8a3747Ddb454cB7a64626C63",
    "ALPACA":"0x8F0528cE5eF7B51152A59745bEfDD91D97091d2F",
    "BIFI":  "0xCa3F508B8e4Dd382eE878A314789373D80A5190A",
    "MDX":   "0x9C65AB58d8d978DB963e63f2bfB7121627e3a739",
    "BSW":   "0x965F527D9159dCe6288a2219DB51fc6Eef120dD1",
    "DODO":  "0x67ee3Cb086F8a16f34beE3ca72FAD36F7Db929e2",
    "ACH":   "0xBc7d6B50616989655AfD682fb42743507003056D",
    "WOM":   "0xAD6742A35fB341A9Cc6ad674738Dd8da98b94Fb2",
    "THE":   "0xF4C8E32EaDEC4BFe97E0F595AdD0f4450a863a5",
    "STG":   "0xB0D502E938ed5f4df2E681fE6E419ff29631d62b",
    "ANKR":  "0xf307910A4c7bbc79691fD374879B36359068993e",
    "TWT":   "0x4B0F1812e5Df2A09796481Ff14017e6005508003",
    "LINK":  "0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD",
    "DOT":   "0x7083609fCE4d1d8Dc0C979AAb8c869Ea2C873402",
    "ADA":   "0x3EE2200Efb3400fAbB9AacF31297cBdD1d435D47",
    "LTC":   "0x4338665CBB7B2485A8855A139b75D5e34AB0DB94",
    "XRP":   "0x1D2F0da169ceB9fC7B3144628dB156f3F6c60dBE",
    "DOGE":  "0xbA2aE424d960c26247Dd6c32edC70B295c744C43",
    "MATIC": "0xCC42724C6683B7E57334c4E856f4c9965ED682bD",
    "SOL":   "0x570A5D26f7765Ecb712C0924E4De545B89fD43dF",
    "ATOM":  "0x0Eb3a705fc54725037CC9e008bDede697f62F335",
    "AVAX":  "0x1CE0c2827e2eF14D5C4f29a091d735A204794041",
    "NEAR":  "0x1Fa4a73a3F0133f0025378af00236f3aBDEE5D63",
    "FIL":   "0x0D8Ce2A99Bb6e3B7Db580eD848240e4a0F9aE153",
    "AAVE":  "0xfb6115445Bff7b52FeB98650C87f44907E58f802",
    "UNI":   "0xBf5140A22578168FD562DCcF235E5D43A02ce9B1",
    "1INCH": "0x111111111117dC0aa78b770fA6A738034120C302",
    "SNX":   "0x9Ac983826058b8a9C7Aa1C9171441191232E8404",
    "YFI":   "0x88f1A5ae2A3BF98AEAF342D26B30a79438c9142e",
    "SUSHI": "0x947950BcC74888a40Ffa2593C5798F11Fc9124C",
    "BAT":   "0x101d82428437127bF1608F699CD651e6Abf9766E",
    "ZIL":   "0xb86AbCb37C3A4B64f74f59301AFF131a1BEcC787",
    "KAVA":  "0x5F88AB06e8dfe89DF127B2430Bba4Af600866035",
    "AXS":   "0x715D400F88C167884bbCc41C5FeA407ed4D2f8A0",
    "SAND":  "0x67b725d7e342d7B611fa85e859Df9697D9378B2e",
    "MANA":  "0x26433c8127d9b4e9B71Eaa15111DF99Ea2EeB2f8",
    "GALA":  "0x7dDEE176F665cD201F93eEDE625770E2fD911990",
    "ALICE": "0xAC51066d7bEC65Dc4589368da368b212745d63E8",
    "PEPE":  "0x25d887Ce7a35172C62FeBFD67a1856F20FaEbB00",
    "SHIB":  "0x2859e4544C4bB03966803b044A93563Bd2D0DD4D",
    "FLOKI": "0xfb5B838b6cfEEdC2873aB27866079AC55363D37A",
    "WIN":   "0xaeF0d72a118ce24feE3cD1d43d383897D05B4e99",
    "HOT":   "0xc0eFf7749b125444953ef89682201Fb8c6A917CD",
    "NFT":   "0x1fC9004eC7E5722891f5f38baE7678efCB11d34D",
    "BTT":   "0x352Cb5E19b12FC216548a2677bD0fce83BaE434B",
    "TRX":   "0xCE7de646e7208a4Ef112cb6ed5038FA6cC6b12e3",
    "INJ":   "0xa2B726B1145A4773F68593CF171187d8EBe4d495",
    "FET":   "0x031b41e504677879370e9DBcF937283A8691Fa7f",
    "LDO":   "0x986854779804799C1d68867F5E03e601E781e41b",
    "PENDLE":"0xb3Ed0A426155B79B898849803E3B36552f7ED507",
    "STX":   "0x60D55F02A771d515e077c9C2403a1ef324885CeC",
    "AXL":   "0x8b1f4432F943c465A973FeDC6d7aa50Fc96f1f65",
    "CHR":   "0xf9CeC8d50f6c8ad3Fb6dcCEC577e05aA32B224FE",
    "BNX":   "0x8C851d1a123Ff703BD1f9dabe631b69902Df5f97",
    "ETC":   "0x3d6545b08693daE087E957cb1180ee38B9e3c25E",
    "LUNC":  "0x156ab3346823B651294766e23e6Cf87254d68962",
    "ZRO":   "0x6985884C4392D348587B19cb9eAAf157F13271cd",
    "RAY":   "0x4b7E2A082B62aDc05BF8Bb5dc23e0A5d0D0Bc36E",  # BSC-pegged Raydium
    "BONK":  "0xA697e272a73744b343528C3Bc4702F2565b2F422",
}

# ── ABIs ───────────────────────────────────────────────────────────────────────
_ROUTER_ABI = json.loads('[{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMin","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokensSupportingFeeOnTransferTokens","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"}]')

_ERC20_ABI = json.loads('[{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"name":"allowance","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"decimals","outputs":[{"type":"uint8"}],"stateMutability":"view","type":"function"}]')

# ── PancakeSwap token list cache ───────────────────────────────────────────────
_pcake_token_cache: dict[str, str] = {}


def _fetch_pancake_token_list():
    """Fetch PancakeSwap extended token list and cache symbol→address mapping."""
    if _pcake_token_cache:
        return
    try:
        resp = requests.get(
            "https://tokens.pancakeswap.finance/pancakeswap-extended.json",
            timeout=10,
        )
        for token in resp.json().get("tokens", []):
            if token.get("chainId") == CHAIN_ID:
                sym = token["symbol"].upper()
                if sym not in _pcake_token_cache:
                    _pcake_token_cache[sym] = Web3.to_checksum_address(token["address"])
        log.info(f"[PCAKE] token list loaded: {len(_pcake_token_cache)} tokens")
    except Exception as e:
        log.warning(f"[PCAKE] token list fetch failed: {e}")


def _resolve_address(symbol: str) -> Optional[str]:
    """Return checksummed BSC contract address for a symbol, or None."""
    sym = symbol.upper()
    if sym in _TOKEN_MAP:
        return Web3.to_checksum_address(_TOKEN_MAP[sym])
    _fetch_pancake_token_list()
    if sym in _pcake_token_cache:
        return _pcake_token_cache[sym]
    return None


# ── Key derivation (from keychain) ─────────────────────────────────────────────

def _read_mnemonic_from_keychain() -> str:
    """Decrypt TWAK wallet.json using password from macOS keychain."""
    try:
        from Crypto.Cipher import AES
    except ImportError:
        os.system("pip install pycryptodome -q")
        from Crypto.Cipher import AES

    pw = subprocess.run(
        ["security", "find-generic-password", "-s", "twak", "-a", "wallet", "-w"],
        capture_output=True, text=True,
    ).stdout.strip()
    if not pw:
        raise RuntimeError("Could not read TWAK password from keychain")

    wallet_path = os.path.expanduser("~/.twak/wallet.json")
    with open(wallet_path) as f:
        data = json.load(f)

    salt       = binascii.unhexlify(data["salt"])
    iv         = binascii.unhexlify(data["iv"])
    auth_tag   = binascii.unhexlify(data["authTag"])
    ciphertext = binascii.unhexlify(data["encryptedMnemonic"])

    key    = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 600000, dklen=32)
    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    return cipher.decrypt_and_verify(ciphertext, auth_tag).decode()


# ── DirectExecutor ─────────────────────────────────────────────────────────────

class DirectExecutor:
    """
    On-chain swap executor via PancakeSwap V2 on BSC.
    Holds private key in memory only — never written to disk.
    """

    def __init__(self):
        mnemonic = _read_mnemonic_from_keychain()
        acc = Account.from_mnemonic(mnemonic, account_path="m/44'/60'/0'/0/0")
        self._key     = acc.key
        self.address  = acc.address
        del mnemonic  # clear from local scope

        for rpc in [BSC_RPC, BSC_RPC_ALT]:
            self.w3 = Web3(Web3.HTTPProvider(rpc))
            if self.w3.is_connected():
                log.info(f"[BSC] Connected via {rpc} | wallet {self.address}")
                break
        else:
            raise RuntimeError("Cannot connect to BSC RPC")

        self.router = self.w3.eth.contract(
            address=Web3.to_checksum_address(PANCAKE_V2),
            abi=_ROUTER_ABI,
        )

        _fetch_pancake_token_list()

    # ── helpers ────────────────────────────────────────────────────────────────

    def _token_contract(self, address: str):
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(address),
            abi=_ERC20_ABI,
        )

    def _decimals(self, token_address: str) -> int:
        try:
            return self._token_contract(token_address).functions.decimals().call()
        except Exception:
            return 18

    def _to_wei(self, amount: float, decimals: int) -> int:
        return int(amount * (10 ** decimals))

    def _gas_price(self) -> int:
        try:
            gp = self.w3.eth.gas_price
            return max(gp, Web3.to_wei(1, "gwei"))
        except Exception:
            return Web3.to_wei(3, "gwei")

    def _ensure_allowance(self, token_address: str, spender: str, amount_wei: int):
        """Approve spender if current allowance is insufficient."""
        token = self._token_contract(token_address)
        allowance = token.functions.allowance(self.address, spender).call()
        if allowance >= amount_wei:
            return
        log.info(f"[APPROVE] {token_address[:10]}… → router (amount={amount_wei})")
        nonce = self.w3.eth.get_transaction_count(self.address)
        tx = token.functions.approve(
            Web3.to_checksum_address(spender),
            2**256 - 1,  # max approval
        ).build_transaction({
            "chainId":  CHAIN_ID,
            "from":     self.address,
            "gas":      80_000,
            "gasPrice": self._gas_price(),
            "nonce":    nonce,
        })
        signed = self.w3.eth.account.sign_transaction(tx, self._key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        log.info(f"[APPROVE] tx sent: {tx_hash.hex()}")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt["status"] != 1:
            raise RuntimeError("Approval transaction reverted")
        log.info("[APPROVE] confirmed")

    def _best_path(self, from_addr: str, to_addr: str, amount_in: int) -> list[str]:
        """Try direct path first, then route via WBNB."""
        wbnb = Web3.to_checksum_address(WBNB)
        direct = [from_addr, to_addr]
        via_wbnb = [from_addr, wbnb, to_addr]

        try:
            out = self.router.functions.getAmountsOut(amount_in, direct).call()
            if out[-1] > 0:
                return direct
        except Exception:
            pass

        try:
            out = self.router.functions.getAmountsOut(amount_in, via_wbnb).call()
            if out[-1] > 0:
                return via_wbnb
        except Exception:
            pass

        return via_wbnb  # default — let swap revert if no liquidity

    # ── public API ─────────────────────────────────────────────────────────────

    def get_price_usd(self, symbol: str) -> float:
        """Get token price in USD via PancakeSwap getAmountsOut (1 token → USDT)."""
        addr = _resolve_address(symbol)
        if not addr:
            return 0.0
        try:
            decimals  = self._decimals(addr)
            usdt_addr = Web3.to_checksum_address(USDT_BSC)
            wbnb_addr = Web3.to_checksum_address(WBNB)
            amount_in = self._to_wei(1.0, decimals)
            usdt_dec  = self._decimals(USDT_BSC)

            # For WBNB itself, use direct path to avoid IDENTICAL_ADDRESSES
            if addr.lower() == wbnb_addr.lower():
                path = [addr, usdt_addr]
            else:
                # Try direct token→USDT first, then via WBNB
                path = self._best_path(addr, usdt_addr, amount_in)

            amounts_out = self.router.functions.getAmountsOut(amount_in, path).call()
            return amounts_out[-1] / (10 ** usdt_dec)
        except Exception as e:
            log.warning(f"[PRICE] {symbol}: {e}")
            return 0.0

    def get_usdt_balance(self) -> float:
        """Return USDT balance of wallet in USD (BSC USDT has 18 decimals)."""
        try:
            token = self._token_contract(USDT_BSC)
            bal   = token.functions.balanceOf(self.address).call()
            dec   = self._decimals(USDT_BSC)
            return bal / (10 ** dec)
        except Exception as e:
            log.warning(f"[BALANCE] USDT: {e}")
            return 0.0

    def swap(
        self,
        amount_usd: float,
        from_token: str,
        to_token:   str,
        slippage:   float = 2.0,
    ) -> dict:
        """
        Execute a swap on PancakeSwap V2.
        amount_usd: for BUY (USDT→token), this is the USD amount to spend.
                    for SELL (token→USDT), this is the token quantity to sell.
        Raises on failure — caller should catch.
        """
        from_addr = _resolve_address(from_token)
        to_addr   = _resolve_address(to_token)

        if not from_addr:
            raise ValueError(f"Unknown token: {from_token}")
        if not to_addr:
            raise ValueError(f"Unknown token: {to_token}")

        from_dec   = self._decimals(from_addr)
        amount_in  = self._to_wei(amount_usd, from_dec)

        # Determine swap path
        path = self._best_path(from_addr, to_addr, amount_in)
        log.info(f"[SWAP] path: {'→'.join([p[:8]+'…' for p in path])}")

        # Get expected output and apply slippage
        try:
            amounts_out = self.router.functions.getAmountsOut(amount_in, path).call()
            amount_out_min = int(amounts_out[-1] * (1 - slippage / 100))
        except Exception:
            amount_out_min = 0  # accept any output if quote fails

        # Approve spending if needed
        self._ensure_allowance(from_addr, PANCAKE_V2, amount_in)

        # Build and send swap tx
        deadline = int(time.time()) + 300  # 5 min
        nonce    = self.w3.eth.get_transaction_count(self.address)

        tx = self.router.functions.swapExactTokensForTokensSupportingFeeOnTransferTokens(
            amount_in,
            amount_out_min,
            path,
            self.address,
            deadline,
        ).build_transaction({
            "chainId":  CHAIN_ID,
            "from":     self.address,
            "gas":      400_000,
            "gasPrice": self._gas_price(),
            "nonce":    nonce,
        })

        signed   = self.w3.eth.account.sign_transaction(tx, self._key)
        tx_hash  = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        log.info(f"[SWAP] tx sent: {tx_hash.hex()}")

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        status  = "confirmed" if receipt["status"] == 1 else "reverted"
        log.info(f"[SWAP] {status} | gas={receipt['gasUsed']} | block={receipt['blockNumber']}")

        if receipt["status"] != 1:
            raise RuntimeError(f"Swap reverted: {tx_hash.hex()}")

        return {
            "status":   status,
            "txHash":   tx_hash.hex(),
            "from":     from_token,
            "to":       to_token,
            "amountIn": amount_usd,
            "gasUsed":  receipt["gasUsed"],
            "block":    receipt["blockNumber"],
        }
