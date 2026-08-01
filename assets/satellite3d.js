window.dash_clientside = Object.assign({}, window.dash_clientside, {
  satellite3d: {
    render: function (satelliteStore, selectedSatellite, activeTab) {
      if (activeTab !== "satellite-3d") {
        return "3d-hidden";
      }

      if (typeof Cesium === "undefined") {
        return "cesium-not-loaded";
      }

      // Required so Cesium can resolve bundled assets (NaturalEarthII, Workers, etc.).
      if (!window.CESIUM_BASE_URL) {
        window.CESIUM_BASE_URL =
          "https://cesium.com/downloads/cesiumjs/releases/1.123/Build/Cesium/";
      }

      const containerId = "cesium-container";
      let state = window.__satelliteCesiumState;

      function createImageryProvider() {
        // Prefer public tile templates that do not require a Cesium Ion token.
        try {
          return new Cesium.UrlTemplateImageryProvider({
            url: "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            maximumLevel: 17,
            credit: "Esri, Maxar, Earthstar Geographics",
          });
        } catch (e1) {
          try {
            return new Cesium.UrlTemplateImageryProvider({
              url: "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
              maximumLevel: 18,
              credit: "CARTO",
            });
          } catch (e2) {
            return new Cesium.TileMapServiceImageryProvider({
              url: Cesium.buildModuleUrl("Assets/Textures/NaturalEarthII"),
            });
          }
        }
      }

      function ensureEarthImagery(viewer) {
        // Remove empty/failed Ion default layers and attach a visible basemap.
        try {
          viewer.imageryLayers.removeAll();
        } catch (e) {
          // ignore
        }
        const provider = createImageryProvider();
        viewer.imageryLayers.addImageryProvider(provider);
        viewer.scene.globe.show = true;
        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString("#1e293b");
        viewer.scene.globe.enableLighting = false;
        viewer.scene.globe.depthTestAgainstTerrain = false;
        if (viewer.scene.skyAtmosphere) {
          viewer.scene.skyAtmosphere.show = true;
        }
        if (viewer.scene.skyBox) {
          viewer.scene.skyBox.show = true;
        }
        viewer.scene.backgroundColor = Cesium.Color.fromCssColorString("#020617");
      }

      if (!state || !state.viewer || state.viewer.isDestroyed()) {
        const imageryProvider = createImageryProvider();
        const viewerOptions = {
          timeline: false,
          animation: false,
          baseLayerPicker: false,
          geocoder: false,
          sceneModePicker: false,
          navigationHelpButton: false,
          fullscreenButton: false,
          homeButton: true,
          infoBox: true,
          selectionIndicator: true,
          shouldAnimate: false,
          terrainProvider: undefined,
        };

        // Cesium 1.104+ prefers baseLayer; keep imageryProvider as fallback.
        if (Cesium.ImageryLayer) {
          viewerOptions.baseLayer = new Cesium.ImageryLayer(imageryProvider);
        } else {
          viewerOptions.imageryProvider = imageryProvider;
        }

        const viewer = new Cesium.Viewer(containerId, viewerOptions);
        ensureEarthImagery(viewer);
        viewer.camera.flyHome(0);

        state = { viewer: viewer, didFlyTo: false, imageryReady: true };
        window.__satelliteCesiumState = state;
      } else if (!state.imageryReady || state.viewer.imageryLayers.length === 0) {
        ensureEarthImagery(state.viewer);
        state.imageryReady = true;
      }

      const viewer = state.viewer;
      viewer.resize();
      viewer.scene.requestRender();

      const records = (satelliteStore && satelliteStore.satellites) || [];
      const selectedNorad =
        selectedSatellite && selectedSatellite.norad_id != null
          ? String(selectedSatellite.norad_id)
          : null;

      // Rebuild entities only when the satellite dataset changes.
      const datasetSignature = [
        satelliteStore && satelliteStore.updated_at
          ? satelliteStore.updated_at
          : "none",
        records.length,
        satelliteStore && satelliteStore.categories
          ? satelliteStore.categories.join(",")
          : "",
      ].join("|");
      const datasetChanged = state.datasetSignature !== datasetSignature;
      if (datasetChanged) {
        viewer.entities.removeAll();
      }

      const defaultColor = Cesium.Color.LIGHTGRAY;
      const categoryColors = {
        "Space Stations": Cesium.Color.fromCssColorString("#ff4d4f"),
        Weather: Cesium.Color.fromCssColorString("#73d13d"),
      };

      if (datasetChanged) {
        records.forEach((satellite) => {
          const isSelected =
            selectedNorad && String(satellite.norad_id) === selectedNorad;
          const color = categoryColors[satellite.category] || defaultColor;

          const description = [
            `<b>${satellite.name || "Unknown"}</b>`,
            `<br>NORAD: ${satellite.norad_id || "Unknown"}`,
            `<br>Category: ${satellite.category || "Unknown"}`,
            `<br>Altitude: ${Number(satellite.elevation_km || 0).toFixed(1)} km`,
            `<br>Country: ${satellite.country || "Unknown"}`,
            `<br>Owner: ${satellite.owner || "Unknown"}`,
            `<br>Purpose: ${satellite.purpose || "Unknown"}`,
          ].join("");

          viewer.entities.add({
            id: "sat-" + String(satellite.norad_id),
            name: satellite.name || "Satellite",
            description: description,
            position: Cesium.Cartesian3.fromDegrees(
              Number(satellite.lon),
              Number(satellite.lat),
              Number(satellite.alt_m || 0)
            ),
            point: {
              pixelSize: isSelected ? 12 : 8,
              color: color,
              outlineColor: Cesium.Color.WHITE,
              outlineWidth: 1,
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
            },
          });
        });
        state.datasetSignature = datasetSignature;
      } else {
        // Only update marker sizes for selected satellite when dataset is unchanged.
        viewer.entities.values.forEach((entity) => {
          if (!entity.id || !entity.point) {
            return;
          }
          const isSelected = selectedNorad && entity.id === "sat-" + selectedNorad;
          entity.point.pixelSize = isSelected ? 12 : 8;
        });
      }

      if (records.length > 0) {
        if (!state.didFlyTo) {
          viewer.flyTo(viewer.entities);
          state.didFlyTo = true;
        } else if (selectedNorad) {
          const selectedEntity = viewer.entities.getById(
            "sat-" + String(selectedNorad)
          );
          if (selectedEntity) {
            viewer.selectedEntity = selectedEntity;
          }
        }
      } else if (!state.didFlyTo) {
        viewer.camera.flyHome(0);
        state.didFlyTo = true;
      }

      return "rendered-" + records.length + "-layers-" + viewer.imageryLayers.length;
    },
  },
});
