// main.js for Digital Notice Board

document.addEventListener("DOMContentLoaded", function () {
  console.log("Digital Notice Board JS loaded");

  // Auto-dismiss Bootstrap alerts after 4 seconds
  const alerts = document.querySelectorAll(".alert");
  alerts.forEach(alert => {
    setTimeout(() => {
      const bsAlert = new bootstrap.Alert(alert);
      bsAlert.close();
    }, 4000);
  });

  // Enhance delete confirmation (extra safety)
  const deleteForms = document.querySelectorAll("form[action*='/notice/'][action$='/delete']");
  deleteForms.forEach(form => {
    form.addEventListener("submit", function (e) {
      if (!confirm("Are you sure you want to delete this notice?")) {
        e.preventDefault();
      }
    });
  });

  // Example: Fetch notices dynamically from API (if we want to render client-side)
  // Uncomment if you'd like to experiment
  /*
  fetch("/api/notices")
    .then(resp => resp.json())
    .then(data => {
      console.log("Fetched notices:", data);
      // You could dynamically inject into DOM here if needed
    })
    .catch(err => console.error("Error fetching notices:", err));
  */
});
