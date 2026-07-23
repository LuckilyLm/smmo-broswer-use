import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider } from "antd";
import App from "./App";
import "./styles.css";
import { ErrorBoundary } from "./ErrorBoundary";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        token: {
          borderRadius: 6,
          colorPrimary: "#14635c",
          fontFamily: "Inter, Segoe UI, Arial, sans-serif"
        }
      }}
    >
      <ErrorBoundary><App /></ErrorBoundary>
    </ConfigProvider>
  </React.StrictMode>
);
