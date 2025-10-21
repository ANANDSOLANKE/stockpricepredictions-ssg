<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>

  <title>{{ stock.name }} ({{ stock.symbol }}) Stock Price Prediction & AI Analysis | {{ exchange }}</title>
  <meta name="description" content="Our AI model predicts a {{ prediction.signal | capitalize }} movement for {{ stock.symbol }} on {{ prediction.date }}. View latest OHLC, model accuracy, and key performance metrics.">

  <!-- Tailwind CDN (kept self-contained; no change to your site-wide CSS) -->
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@100..900&display=swap" rel="stylesheet">

  <style>
    body { font-family: "Inter", system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji";}
    .trust-card { box-shadow: 0 4px 10px rgba(0,0,0,.08); transition: transform .3s; }
    .trust-card:hover { transform: translateY(-5px); }
    .win { background:#d4edda; color:#155724; font-weight:700; }
    .loss { background:#f8d7da; color:#721c24; font-weight:700; }
    .signal-bullish { background: linear-gradient(135deg,#10b981 0%,#059669 100%); }
    .signal-bearish { background: linear-gradient(135deg,#ef4444 0%,#b91c1c 100%); }
  </style>
</head>
<body class="bg-gray-50">

  <!-- SEO structured data -->
  <script type="application/ld+json">
  {
    "@context":"https://schema.org",
    "@type":"NewsArticle",
    "mainEntityOfPage":{"@type":"WebPage","@id":"{{ page_url }}"},
    "headline":"AI Prediction: {{ stock.name }} ({{ stock.symbol }}) for {{ prediction.date }}",
    "datePublished":"{{ last_build_iso }}",
    "dateModified":"{{ last_build_iso }}",
    "author":{"@type":"Organization","name":"Stock Price Predictions"},
    "publisher":{"@type":"Organization","name":"Stock Price Predictions",
      "logo":{"@type":"ImageObject","url":"https://placehold.co/60x60/007bff/ffffff?text=SPL"} },
    "description":"Our AI model predicts a {{ prediction.signal | capitalize }} movement for {{ stock.symbol }} on {{ prediction.date }}."
  }
  </script>

  <div class="container mx-auto p-4 md:p-8 max-w-6xl">

    <!-- Header -->
    <header class="bg-white p-4 md:p-6 rounded-xl shadow-lg flex flex-col md:flex-row justify-between items-center mb-6 border-b-4 border-emerald-500">
      <div class="flex items-center gap-4">
        <div class="w-10 h-10 bg-yellow-500 rounded-lg flex items-center justify-center text-white font-bold text-xl">
          {{ stock.symbol[:2] }}
        </div>
        <div>
          <h2 class="text-2xl md:text-3xl font-extrabold text-gray-800">
            {{ stock.name }} <span class="text-gray-500 font-semibold text-sm">({{ stock.symbol }})</span>
          </h2>
          <p class="text-sm text-gray-600">
            {{ region }} · {{ country }} · {{ exchange }} |
            <span class="font-medium text-xs">Last Updated: {{ last_build_iso }}</span>
          </p>
        </div>
      </div>
      {% if price %}
      <div class="text-right mt-4 md:mt-0">
        <p class="text-4xl font-bold {{ price.change_pct >= 0 and 'text-emerald-600' or 'text-red-600' }}">
          {{ price.currency_symbol }}{{ "%0.2f"|format(price.close) }}
        </p>
        <p class="text-lg font-semibold {{ price.change_pct >= 0 and 'text-emerald-600' or 'text-red-600' }}">
          {{ "%0.2f"|format(price.change_pct) }}%
        </p>
      </div>
      {% endif %}
    </header>

    <!-- Prediction hero -->
    <div class="prediction-block {{ prediction.signal == 'bullish' and 'signal-bullish' or 'signal-bearish' }} text-white p-6 md:p-10 rounded-xl mb-8 shadow-2xl">
      <h1 class="text-2xl md:text-4xl font-light mb-2">
        AI Prediction: {{ stock.name }} ({{ stock.symbol }}) for {{ prediction.date }}
      </h1>
      <p class="text-lg font-medium opacity-80 uppercase tracking-widest mb-2">Next-Day Signal</p>
      <div class="text-7xl md:text-8xl font-black uppercase tracking-widest mb-6">
        {{ prediction.signal | upper }}
      </div>
      <p class="italic text-sm opacity-90 mb-6">
        Based on yesterday's OHLC data and our proprietary model.
      </p>

      <div class="ohlc-data bg-white text-gray-800 font-mono p-3 rounded-lg shadow-inner text-center text-sm md:text-lg mx-auto max-w-2xl">
        <span class="font-bold">OHLC:</span>
        O {{ price and "%0.2f"|format(price.open) or "—" }}
        | H {{ price and "%0.2f"|format(price.high) or "—" }}
        | L {{ price and "%0.2f"|format(price.low) or "—" }}
        | C {{ price and "%0.2f"|format(price.close) or "—" }}
      </div>
    </div>

    <!-- Trust cards -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
      <div class="trust-card bg-white p-6 rounded-xl border-t-4 border-blue-600">
        <h3 class="text-xl font-bold text-blue-600 mb-2">Model Performance</h3>
        <div class="text-5xl font-extrabold text-emerald-600 mb-1">
          {{ last7.accuracy_pct }}
        </div>
        <p class="text-sm text-gray-700">7-Day Accuracy ({{ last7.win_count }}/{{ last7.total }})</p>
        <p class="text-xs text-gray-500 mt-2">*Demonstrates Experience*</p>
      </div>

      <div class="trust-card bg-white p-6 rounded-xl border-t-4 border-blue-600">
        <h3 class="text-xl font-bold text-blue-600 mb-2">Our Methodology</h3>
        <p class="text-sm text-gray-700 mb-3">
          We analyze 50+ factors (volume, RSI, MACD, support/resistance) via our deep learning model.
        </p>
        <a href="#" class="text-blue-500 hover:text-blue-700 font-semibold text-sm">Read Our Full Process →</a>
      </div>

      <div class="trust-card bg-white p-6 rounded-xl border-t-4 border-blue-600">
        <h3 class="text-xl font-bold text-blue-600 mb-2">Important Disclosures</h3>
        <p class="text-xs text-red-600 p-2 border border-red-300 bg-red-50 rounded-lg">
          This is NOT financial advice. For informational purposes only. Trading carries inherent risk.
        </p>
        <p class="text-xs text-gray-500 mt-2">*Authority & Trustworthiness*</p>
      </div>
    </div>

    <!-- Last 7 days table -->
    <div class="bg-white p-6 rounded-xl shadow-lg mb-8">
      <h2 class="text-2xl font-semibold text-gray-800 mb-4">Model vs. Actual: Last 7 Days Performance</h2>
      <div class="overflow-x-auto">
        <table class="w-full min-w-max rounded-lg overflow-hidden border">
          <thead>
            <tr class="text-sm font-semibold text-gray-700 uppercase bg-gray-100">
              <th class="p-3 border-r">Date</th>
              <th class="p-3 border-r">AI Prediction</th>
              <th class="p-3 border-r">Actual Movement</th>
              <th class="p-3">Result</th>
            </tr>
          </thead>
          <tbody>
            {% for r in last7.rows %}
              <tr class="border-t">
                <td class="p-3 border-r">{{ r.date }}</td>
                <td class="p-3 border-r">{{ r.prediction }}</td>
                <td class="p-3 border-r">{{ r.actual }}</td>
                <td class="p-3 {{ r.result|lower }}">{{ r.result }}</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>

    <!-- Optional long-form analysis block (kept short) -->
    <div class="bg-white p-6 rounded-xl shadow-lg">
      <h2 class="text-2xl font-semibold text-gray-800 mb-4">In-Depth Technical Context</h2>
      <p class="text-gray-700">
        This view summarizes the model’s next-day directional call using the latest market close and
        recent movement. Use alongside your risk management.
      </p>
    </div>
  </div>
</body>
</html>
