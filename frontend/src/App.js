import React, { useEffect, useState } from "react";
import axios from "axios";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
} from "recharts";
import "./App.css";
import bannerImage from "./banner.jpg";

function App() {
  const [token, setToken] = useState(null);
  const [stocks, setStocks] = useState(null);
  const [symbol, setSymbol] = useState("");
  const [searchedStock, setSearchedStock] = useState(null);
  const [portfolio, setPortfolio] = useState([]);
  const [priceHistory, setPriceHistory] = useState({});

  const logout = () => {
    localStorage.removeItem("id_token");
    const logoutUrl =
      `https://us-east-2ffnvtooil.auth.us-east-2.amazoncognito.com/logout` +
      `?client_id=1c5q0l5q7mrksqofaeq39j3ukh` +
      `&redirect_uri=http://localhost:3000/&response_type=token&scope=email+openid+phone`;
    window.location.href = logoutUrl;
  };

  const login = () => {
    window.location.href =
      "https://us-east-2ffnvtooil.auth.us-east-2.amazoncognito.com/login" +
      "?response_type=token" +
      "&client_id=1c5q0l5q7mrksqofaeq39j3ukh" +
      "&redirect_uri=http://localhost:3000/" +
      "&scope=email+openid+phone";
  };

  useEffect(() => {
    const hash = window.location.hash;
    if (hash && hash.includes("id_token")) {
      const params = new URLSearchParams(hash.slice(1));
      const idToken = params.get("id_token");
      if (idToken) {
        localStorage.setItem("id_token", idToken);
        setToken(idToken);
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    } else {
      const savedToken = localStorage.getItem("id_token");
      if (savedToken) setToken(savedToken);
    }
  }, []);

  // Load all available tracked stocks (real-time prices)
  useEffect(() => {
    if (token) {
      axios
        .get("http://127.0.0.1:5000/api/stocks", {
          headers: { Authorization: `Bearer ${token}` },
        })
        .then((res) => setStocks(res.data))
        .catch((err) => console.error("API Error", err));
    }
  }, [token]);

  // 🔁 Load portfolio from backend
  useEffect(() => {
    if (token) {
      axios
        .get("http://127.0.0.1:5000/api/portfolio", {
          headers: { Authorization: `Bearer ${token}` },
        })
        .then((res) => setPortfolio(res.data))
        .catch((err) => console.error("Portfolio fetch failed", err));
    }
  }, [token]);

  // 🔁 Fetch price history for each stock in portfolio
  useEffect(() => {
    portfolio.forEach((sym) => {
      if (!priceHistory[sym]) {
        axios
          .get(`http://127.0.0.1:5000/api/stocks/history?symbol=${sym}`, {
            headers: { Authorization: `Bearer ${token}` },
          })
          .then((res) => {
            setPriceHistory((prev) => ({ ...prev, [sym]: res.data }));
          })
          .catch((err) => console.error("Price history error", err));
      }
    });
  }, [portfolio, token]);

  const searchStock = () => {
    if (!symbol) return;
    axios
      .get(`http://127.0.0.1:5000/api/searchstock?symbol=${symbol}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => setSearchedStock(res.data))
      .catch((err) => console.error("Stock search failed", err));
  };

  const addToPortfolio = () => {
    if (!symbol) return;
    axios
      .post(
        "http://127.0.0.1:5000/api/portfolio",
        { symbol },
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      )
      .then(() => {
        if (!portfolio.includes(symbol)) {
          setPortfolio([...portfolio, symbol]);
        }
        setSymbol("");
      })
      .catch((err) => console.error("Add to portfolio failed", err));
  };

  if (!token) {
    return (
      <div className="login-container">
        <img src={bannerImage} alt="Stock Tracker Banner" className="banner-image" />
        <div className="welcome-box">
          <h2>🔐 Please Login to Continue</h2>
          <p className="intro-text">
            Welcome to <strong>Stock Track</strong> — your comprehensive platform for monitoring
            real-time market data, researching stocks, and tracking your personalized portfolio with
            detailed historical charts.
          </p>
          <button onClick={login} className="login-button">Login with Cognito</button>
        </div>
      </div>
    );
  }

  if (!stocks) return <p className="loading-text">Loading stock data...</p>;

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>📈 Stock Tracker Dashboard</h1>
        <button onClick={logout}>Logout</button>
      </header>

      <section className="module-window">
        <div className="search-controls">
          <input
            type="text"
            placeholder="Enter stock symbol (e.g. AAPL)"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          />
          <button onClick={searchStock}>Search</button>
          <button onClick={addToPortfolio}>Add to Portfolio</button>
        </div>

        {searchedStock && (
          <div className="stock-info">
            <h3>🔎 {searchedStock.symbol}</h3>
            <p>Price: ${searchedStock.price}</p>
            <p>Change: {searchedStock.change}%</p>
          </div>
        )}
      </section>

      <section className="module-window">
        <h2>💼 My Portfolio</h2>
        {portfolio.length === 0 ? (
          <p>Your portfolio is empty.</p>
        ) : (
          portfolio.map((sym) => (
            <div key={sym} className="portfolio-item">
              <h3>{sym} - Price History</h3>
              {priceHistory[sym] ? (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={priceHistory[sym]}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis domain={["auto", "auto"]} />
                    <Tooltip />
                    <Line type="monotone" dataKey="price" stroke="#10b981" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p>Loading chart...</p>
              )}
            </div>
          ))
        )}
      </section>

      <section className="module-window">
        <h2>🌐 All Tracked Stocks</h2>
        <ul className="stock-grid">
          {Object.entries(stocks).map(([symbol, price]) => (
            <li key={symbol} className="stock-card">
              {symbol}: ${price}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export default App;
