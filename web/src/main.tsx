import React from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { App } from "./App";

const host = document.getElementById("root");
if (!host) throw new Error("#root is missing from index.html");
createRoot(host).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
