import requests
import json
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Phân tích lời/lỗ Token Solana", layout="wide")
st.title("📊 Phân tích lời/lỗ Token Solana (cập nhật theo giao dịch mới)")

wallet = st.text_input("🔑 Nhập địa chỉ ví Solana:")
helius_api_key = "72ec3ea1-3e2e-4c72-9f5e-21cd6ec73277"
refresh = st.button("🔄 Quét lại và cập nhật giá mới")

@st.cache_data(show_spinner=False)
def get_all_new_transactions(wallet, api_key, known_last_signature=None, limit_per_page=25):
    all_txs = []
    base_url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions?api-key={api_key}&limit={limit_per_page}"
    next_signature = None
    stop = False

    while not stop:
        url = base_url
        if next_signature:
            url += f"&before={next_signature}"

        res = requests.get(url)
        txs = res.json()

        if not txs:
            break

        for tx in txs:
            if tx["signature"] == known_last_signature:
                stop = True
                break
            all_txs.append(tx)

        next_signature = txs[-1]["signature"]

        if len(txs) < limit_per_page:
            break

    return all_txs

@st.cache_data(show_spinner=False)
def fetch_tokens(wallet, api_key):
    url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"
    payload = {
        "jsonrpc": "2.0",
        "id": "get-assets",
        "method": "getAssetsByOwner",
        "params": {
            "ownerAddress": wallet,
            "page": 1,
            "limit": 1000,
            "displayOptions": {"showFungible": True}
        }
    }
    res = requests.post(url, json=payload).json()
    items = res.get("result", {}).get("items", [])
    owned_tokens = []
    for asset in items:
        token_info = asset.get("token_info", {})
        balance = float(token_info.get("balance", 0))
        decimals = int(token_info.get("decimals", 0))
        mint = asset.get("id")
        if balance > 0 and mint != "So11111111111111111111111111111111111111112":
            owned_tokens.append({
                "mint": mint,
                "balance": balance / (10 ** decimals),
                "raw_balance": balance,
                "decimals": decimals
            })
    return owned_tokens

@st.cache_data(show_spinner=False)
def get_cached_data(wallet, api_key):
    tokens = fetch_tokens(wallet, api_key)
    transactions = get_all_new_transactions(wallet, api_key)
    return {
        "tokens": tokens,
        "transactions": transactions,
        "last_signature": transactions[0]["signature"] if transactions else None
    }

def get_token_price(mint):
    try:
        quote = requests.get("https://quote-api.jup.ag/v6/quote", params={
            "inputMint": mint,
            "outputMint": "So11111111111111111111111111111111111111112",
            "amount": 1_000_000,
            "slippageBps": 50
        }, timeout=5).json()
        return int(quote["outAmount"]) / 1e9
    except:
        return None

if wallet:
    with st.spinner("📥 Đang kiểm tra dữ liệu ví..."):
        data = get_cached_data(wallet, helius_api_key)
        tokens = data["tokens"]
        transactions = data["transactions"]

    st.success(f"✅ Dữ liệu ví {wallet[:6]}... đã được tải.")
    st.markdown("---")

    st.subheader("📊 Bảng phân tích lời/lỗ từng token:")
    df = pd.DataFrame(columns=["STT", "Token", "Số lượng", "Giá mua (SOL)", "Giá hiện tại (SOL)", "Chênh lệch (SOL)", "Phần trăm", "Trạng thái"])
    placeholder = st.empty()

    for idx, token in enumerate(tokens, start=1):
        mint_out = token["mint"]
        current_balance = token["balance"]
        df.loc[len(df)] = [idx, mint_out, f"{current_balance:.4f}", "...", "...", "...", "...", "⏳"]
        placeholder.dataframe(df)

        sol_sent = 0
        token_received = 0
        for tx in transactions:
            transfers = tx.get("tokenTransfers", [])
            sol_in_tx = 0
            token_in_tx = 0
            for transfer in transfers:
                mint = transfer.get("mint")
                amount = float(transfer.get("tokenAmount", 0))
                if mint == "So11111111111111111111111111111111111111112" and transfer.get("fromUserAccount") == wallet:
                    sol_in_tx += amount
                if mint == mint_out and transfer.get("toUserAccount") == wallet:
                    token_in_tx += amount
            if sol_in_tx and token_in_tx:
                sol_sent = sol_in_tx
                token_received = token_in_tx
                break

        if not (sol_sent and token_received):
            df.at[idx - 1, "Giá mua (SOL)"] = "⚠️ Không tìm thấy"
            df.at[idx - 1, "Trạng thái"] = "❌"
            placeholder.dataframe(df)
            continue

        price_bought = sol_sent / token_received
        current_price = get_token_price(mint_out)
        if not current_price:
            df.at[idx - 1, "Giá mua (SOL)"] = f"{price_bought:.12f}"
            df.at[idx - 1, "Giá hiện tại (SOL)"] = "⚠️ Không có"
            df.at[idx - 1, "Trạng thái"] = "❌"
            placeholder.dataframe(df)
            continue

        total_buy = price_bought * current_balance
        total_now = current_price * current_balance
        diff = total_now - total_buy
        percent = (diff / total_buy) * 100
        status = "🟢 LỜI" if diff > 0 else "🔴 LỖ"

        df.at[idx - 1, "Giá mua (SOL)"] = f"{price_bought:.12f}"
        df.at[idx - 1, "Giá hiện tại (SOL)"] = f"{current_price:.12f}"
        df.at[idx - 1, "Chênh lệch (SOL)"] = round(diff, 6)
        df.at[idx - 1, "Phần trăm"] = f"{percent:.2f}%"
        df.at[idx - 1, "Trạng thái"] = status
        placeholder.dataframe(df)

    st.success("✅ Phân tích hoàn tất!")
