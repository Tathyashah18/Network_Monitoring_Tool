/* ============================================================
   NETWORK MONITORING DASHBOARD
   AUTO REFRESH + LIVE UPTIME
   ============================================================ */


/* ============================================================
   FORMAT UPTIME
   ============================================================ */

function formatUptime(totalSeconds) {

    totalSeconds = Math.max(
        0,
        Math.floor(totalSeconds)
    );

    const days = Math.floor(
        totalSeconds / 86400
    );

    totalSeconds %= 86400;

    const hours = Math.floor(
        totalSeconds / 3600
    );

    totalSeconds %= 3600;

    const minutes = Math.floor(
        totalSeconds / 60
    );

    const seconds = totalSeconds % 60;


    const hh = String(hours).padStart(
        2,
        "0"
    );

    const mm = String(minutes).padStart(
        2,
        "0"
    );

    const ss = String(seconds).padStart(
        2,
        "0"
    );


    if (days > 0) {

        return (
            days +
            "d " +
            hh +
            ":" +
            mm +
            ":" +
            ss
        );

    }


    return (
        hh +
        ":" +
        mm +
        ":" +
        ss
    );
}


/* ============================================================
   UPDATE LIVE UPTIME
   ============================================================ */

function updateUptime() {

    const cards = document.querySelectorAll(
        ".device-card"
    );


    cards.forEach(function(card) {

        const uptimeElement =
            card.querySelector(
                ".uptime-counter"
            );


        if (!uptimeElement) {
            return;
        }


        /* ----------------------------------------------------
           IMPORTANT:
           NEVER CHANGE UPTIME OF OFFLINE DEVICES
           ---------------------------------------------------- */

        if (
            card.classList.contains(
                "offline-card"
            )
        ) {

            return;
        }


        /* ----------------------------------------------------
           GET ONLINE SINCE
           ---------------------------------------------------- */

        const onlineSince =
            card.getAttribute(
                "data-online-since"
            );


        if (!onlineSince) {
            return;
        }


        /* ----------------------------------------------------
           CONVERT ONLINE SINCE TO TIMESTAMP
           ---------------------------------------------------- */

        const startTime =
            new Date(
                onlineSince
            ).getTime();


        if (isNaN(startTime)) {
            return;
        }


        /* ----------------------------------------------------
           CURRENT TIME
           ---------------------------------------------------- */

        const currentTime =
            new Date().getTime();


        /* ----------------------------------------------------
           CALCULATE LIVE UPTIME
           ---------------------------------------------------- */

        const uptimeSeconds =
            (
                currentTime -
                startTime
            ) / 1000;


        /* ----------------------------------------------------
           DISPLAY UPTIME
           ---------------------------------------------------- */

        uptimeElement.textContent =
            formatUptime(
                uptimeSeconds
            );

    });
}


/* ============================================================
   UPDATE CURRENT TIME
   ============================================================ */

function updateCurrentTime() {

    const currentTimeElement =
        document.getElementById(
            "current-time"
        );


    if (!currentTimeElement) {
        return;
    }


    const now = new Date();


    const timeString =
        now.toLocaleTimeString();


    currentTimeElement.textContent =
        timeString;
}


/* ============================================================
   SEARCH DEVICES
   ============================================================ */

function setupSearch() {

    const searchInput =
        document.getElementById(
            "searchInput"
        );


    if (!searchInput) {
        return;
    }


    searchInput.addEventListener(
        "input",
        function() {

            const searchValue =
                searchInput.value
                    .toLowerCase()
                    .trim();


            const cards =
                document.querySelectorAll(
                    ".device-card"
                );


            cards.forEach(
                function(card) {

                    const text =
                        card.textContent
                            .toLowerCase();


                    if (
                        text.includes(
                            searchValue
                        )
                    ) {

                        card.style.display =
                            "";

                    } else {

                        card.style.display =
                            "none";
                    }

                }
            );

        }
    );
}


/* ============================================================
   INITIALIZATION
   ============================================================ */

document.addEventListener(
    "DOMContentLoaded",
    function() {

        updateUptime();

        updateCurrentTime();

        setupSearch();

    }
);


/* ============================================================
   LIVE UPDATE EVERY SECOND
   ============================================================ */

setInterval(
    updateUptime,
    1000
);


setInterval(
    updateCurrentTime,
    1000
);