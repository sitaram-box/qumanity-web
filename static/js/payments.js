// Shared Razorpay payment flow (donations + the registration-time donation), used by dashboard.js
// and register.js. Server-side: payment_core.py / app.py's /api/payment/order + /api/payment/verify.
(function () {
  "use strict";

  // order = the JSON body from POST /api/payment/order.
  // onSuccess(creditedBody) / onError(Error) mirror every other fetch handler in this app.
  function payWithRazorpay(order, description, onSuccess, onError) {
    if (order.mode === "simulated") {
      // No RAZORPAY_KEY_ID/SECRET configured on this server yet -- same instant-credit dev
      // fallback the old simulated /api/wallet/donate always used.
      verify({ local_order_id: order.local_order_id }, onSuccess, onError);
      return;
    }
    if (typeof Razorpay === "undefined") {
      onError(new Error("Payment widget failed to load. Check your connection and try again."));
      return;
    }
    var rzp = new Razorpay({
      key: order.key_id,
      amount: order.amount_paise,
      currency: order.currency,
      order_id: order.razorpay_order_id,
      name: "Qumanity",
      description: description,
      handler: function (response) {
        verify({
          local_order_id: order.local_order_id,
          razorpay_payment_id: response.razorpay_payment_id,
          razorpay_order_id: response.razorpay_order_id,
          razorpay_signature: response.razorpay_signature,
        }, onSuccess, onError);
      },
      modal: { ondismiss: function () { onError(new Error("Payment cancelled.")); } },
    });
    rzp.open();
  }

  function verify(body, onSuccess, onError) {
    fetch("/api/payment/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (r) { return r.json().then(function (b) { return { ok: r.ok, body: b }; }); })
      .then(function (result) {
        if (!result.ok) throw new Error(result.body.error || "Payment verification failed");
        onSuccess(result.body);
      })
      .catch(onError);
  }

  window.QMPayments = { payWithRazorpay: payWithRazorpay };
})();
