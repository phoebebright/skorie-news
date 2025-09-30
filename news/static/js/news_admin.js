


  function flash(kind, msg) {
    $("#subs-alert").removeClass("d-none alert-success alert-danger alert-warning")
                    .addClass(`alert alert-${kind}`).text(msg);
  }

  function setBusy($btn, busy) {
    $btn.prop("disabled", busy);
    if (busy) { $btn.data("orig", $btn.text()); $btn.text("Working…"); }
    else { $btn.text($btn.data("orig") || $btn.text()); }
  }

  // ---- Subscribe (create a new Subscription row) ----
  $(document).on("click", ".subscribe", function() {
    const $btn = $(this);

    const subscribe_url = $(this).closest('tr').data('subscribe_url');
    const newsletterId = $(this).closest('tr').data('newsletter_id');
    setBusy($btn, true);

    const payload = {
        user_keycloak_id: userid,
        newsletter: newsletterId, // expects PK
    }

    $.ajax({
      url: subscribe_url,
      method: "POST",
      data: payload,
      success: function(row) {
        // Update row inline from API response
        $tr.attr("data-subscription-id", row.id);
        $tr.find(".status-cell").html('<span class="badge bg-success">Subscribed</span>');
        $tr.find(".subscribed-cell").text(row.subscribe_date || "");
        $tr.find(".unsubscribed-cell").text("");
        $tr.find(".action-cell").html(
          `<button class="btn btn-sm btn-outline-danger js-unsubscribe" >Unsubscribe</button>`
        );
        flash("success", "Subscribed.");
      },
      error: function(xhr) {
        flash("danger", xhr.responseJSON?.detail || "Subscribe failed.");
      },
      complete: function(){ setBusy($btn, false); }
    });
  });

  // ---- Unsubscribe (per-row action) ----
  $(document).on("click", ".js-unsubscribe", function() {
    const $btn = $(this);
    const subId = $(this).data("subscription_id");
    const unsubscibe_url = $(this).closest('tr').data('unsubscribe_url');
    const subscribe_url = $(this).closest('tr').data('subscribe_url');
    const newsletterId = $(this).closest('tr').data('news-id');
    setBusy($btn, true);

    $.ajax({
      url: unsubscibe_url,
      method: "PATCH",
            data: JSON.stringify({
        newsletter: newsletterId, // expects PK
      }),
      success: function(row) {
        const $tr = $btn.closest("tr");
        $tr.find(".status-cell").html('<span class="badge bg-danger">Unsubscribed</span>');
        $tr.find(".unsubscribed-cell").text(row.unsubscribe_date || "");
        $tr.find(".action-cell").html(
          `<button class="btn btn-sm btn-outline-success js-resubscribe" >Resubscribe</button>`
        );
        flash("success", "Unsubscribed.");
      },
      error: function(xhr) {
        flash("danger", xhr.responseJSON?.detail || "Unsubscribe failed.");
      },
      complete: function(){ setBusy($btn, false); }
    });
  });

  // ---- Resubscribe (per-row action) ----
  $(document).on("click", ".js-resubscribe", function() {
    const $btn = $(this);
    const subId = $(this).closest('tr').data("subscription_id");
    const unsubscibe_url = $(this).closest('tr').data('unsubscribe_url');
    const subscribe_url = $(this).closest('tr').data('subscribe_url');
    const newsletterId = $(this).closest('tr').data('news-id');
    setBusy($btn, true);

    $.ajax({
      url: subscribe_url,
      method: "PATCH",
      success: function(row) {
        const $tr = $btn.closest("tr");
        $tr.find(".status-cell").html('<span class="badge bg-success">Subscribed</span>');
        $tr.find(".subscribed-cell").text(row.subscribe_date || "");
        $tr.find(".unsubscribed-cell").text("");
        $tr.find(".action-cell").html(
          `<button class="btn btn-sm btn-outline-danger js-unsubscribe">Unsubscribe</button>`
        );
        flash("success", "Resubscribed.");
      },
      error: function(xhr) {
        flash("danger", xhr.responseJSON?.detail || "Resubscribe failed.");
      },
      complete: function(){ setBusy($btn, false); }
    });
  });
